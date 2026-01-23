"""
JSON Schema → Flow-based constrained generation mod.

This mod inspects schemas provided at runtime (via get_schemas()) and builds
FlowQuestions that constrain each field according to its JSON Schema type:

- string → CharsStrat(STRING, stop="\n")
- integer/number → CharsStrat(NUMERIC, stop="\n")
- boolean → ChoicesStrat(["true", "false"])
- array (of strings) → ListStrat(open="[", close="]", wrap='"', sep=", ", end_with="\n",
  elements=CharsStrat(STRING, stop='"'))
- object → recursively step into properties and generate leaves using the above

Prompts include the variable name and description (when provided) and specify
how to end generation (e.g., “end with a newline” for scalars, or “close the
list then newline” for arrays). Each question uses EraseMode.ALL so prompts and
intermediate answers are erased from the visible transcript; only the final
JSON is emitted via route_output.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Callable

logger = logging.getLogger(__name__)

from jsonpath_ng.ext import parse as jsonpath_parse
from quote_mod_sdk import mod, Prefilled, ForwardPass, Added, get_conversation
from quote_mod_sdk.flow import FlowEngine, FlowQuestion, route_output, route_tool
from quote_mod_sdk.self_prompt import EraseMode
from quote_mod_sdk.strategies.strategy_constructor import (
    ChoicesStrat,
    ListStrat,
    CharsStrat,
    CharsMode,
)
from .pattern_strategies import PatternStrat
from quote_mod_sdk import get_schemas  # pyright: ignore[reportMissingImports]
from shared.types import AdjustedLogits

@dataclass
class AppState:
    # FlowState protocol
    request_id: str
    current_question: Optional[FlowQuestion] = None
    pending_route: Optional[Any] = None
    answers: Dict[str, str] = field(default_factory=dict)
    data: Dict[str, Any] = field(default_factory=dict)

import re

def _sanitize_qname(text: str) -> str:
    return (
        text.replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace("[", "_")
        .replace("]", "_")
        .replace("<", "_")
        .replace(">", "_")
    )


def validate_field_is_sat(field_schema: Dict[str, Any]) -> bool:
    """Return True if this schema is satisfiable by the generator.

    This is a conservative check tailored to the subset of JSON Schema we
    implement. It focuses on combinations we definitely cannot satisfy, such as:
    - array/object types with enum (exact-structure enums we don't synthesize),
    - unions (anyOf/oneOf) where all branches are unsatisfiable,
    - objects whose required properties are themselves unsatisfiable.
    """
    if not isinstance(field_schema, dict):
        return True

    # Union: satisfiable if at least one branch is satisfiable.
    union = field_schema.get("anyOf") or field_schema.get("oneOf")
    if isinstance(union, list) and union:
        for alt in union:
            if isinstance(alt, dict) and validate_field_is_sat(alt):
                return True
        return False

    ftype = _type_of(field_schema)
    # Arrays/objects with enum are treated as unsatisfiable for this generator.
    if ftype in ("array", "object"):
        if field_schema.get("enum") is not None:
            return False
        if ftype == "object":
            props = field_schema.get("properties") or {}
            req = field_schema.get("required") or []
            if isinstance(props, dict) and isinstance(req, list):
                for name in req:
                    if not isinstance(name, str):
                        continue
                    subs = props.get(name)
                    if isinstance(subs, dict) and not validate_field_is_sat(subs):
                        return False
        return True

    # Scalars: mostly satisfiable; if they embed an object-like sub-schema via
    # properties/required, ensure that nested required props are satisfiable.
    props = field_schema.get("properties") or {}
    req = field_schema.get("required") or []
    if isinstance(props, dict) and isinstance(req, list):
        for name in req:
            if not isinstance(name, str):
                continue
            subs = props.get(name)
            if isinstance(subs, dict) and not validate_field_is_sat(subs):
                return False
    return True


def _path_to_jsonpath(path: List[str]) -> str:
    """Convert an internal path (list of segments) to a JSONPath string."""
    expr = "$"
    for seg in path:
        # Treat purely numeric segments as array indices.
        try:
            idx = int(seg)
            expr += f"[{idx}]"
            continue
        except Exception:
            pass
        # Use bracket-quoted field access to avoid conflicts with special chars.
        esc = seg.replace("\\", "\\\\").replace('"', '\\"')
        expr += f'["{esc}"]'
    return expr


def _set_nested(d: Dict[str, Any], path: List[str], value: Any) -> None:
    """Assign value at the given path using jsonpath_ng for navigation.

    We rely on jsonpath_ng for the actual targeting logic and fall back to a
    minimal container-creation pass when no nodes are matched yet.
    """
    logger.debug("_set_nested: d=%s, path=%s, value=%s", d, path, value)
    if not path:
        return

    expr_str = _path_to_jsonpath(path)
    logger.debug("expr str: %s", expr_str)
    expr = jsonpath_parse(expr_str)
    logger.debug("expr: %s", expr)

    # First attempt: update existing nodes matching the path.
    matches = list(expr.find(d))
    logger.debug("matches: %s", matches)
    if matches:
        expr.update(d, value)
        logger.debug("updated d: %s", d)
        return

    # If nothing matched, create parent containers manually, then retry update.
    parent_path = path[:-1]
    leaf = path[-1]
    cur: Any = d
    for i, seg in enumerate(parent_path):
        # Determine if this key is an array index.
        try:
            idx = int(seg)
            is_index = True
        except Exception:
            is_index = False

        if is_index:
            if not isinstance(cur, list):
                # Replace non-list containers with a list.
                raise TypeError("Invalid path: numeric index without list container")
            while len(cur) <= idx:
                cur.append({})
            if not isinstance(cur[idx], (dict, list)):
                cur[idx] = {}
            cur = cur[idx]
        else:
            if not isinstance(cur, dict):
                raise TypeError("Invalid path: dict key without dict container")
            if seg not in cur or not isinstance(cur[seg], (dict, list)):
                cur[seg] = {}
            cur = cur[seg]

    # For the leaf, if it's an index into a list we ensure the list shape;
    # otherwise we rely on dict assignment.
    try:
        leaf_idx = int(leaf)
        leaf_is_index = True
    except Exception:
        leaf_is_index = False

    if leaf_is_index:
        if not isinstance(cur, list):
            raise TypeError("Invalid path: numeric index without list container")
        while len(cur) <= leaf_idx:
            cur.append(None)
        cur[leaf_idx] = value
    else:
        if not isinstance(cur, dict):
            raise TypeError("Invalid path: dict key without dict container")
        cur[leaf] = value

def _type_of(schema: Dict[str, Any]) -> Optional[str]:
    t = schema.get("type")
    if isinstance(t, list):
        # pick first concrete type if a union (simplification)
        for cand in t:
            if isinstance(cand, str):
                return cand
        return None
    return t if isinstance(t, str) else None


def _json_pointer_resolve(root: Dict[str, Any], pointer: str) -> Optional[Dict[str, Any]]:
    """Resolve a JSON Pointer against root. Supports fragments like '#/$defs/X'."""
    try:
        ptr = pointer or ""
        if ptr.startswith("#"):
            ptr = ptr[1:]
        if not ptr:
            return root
        if not ptr.startswith("/"):
            # Not a JSON pointer; unsupported external ref
            return None
        cur: Any = root
        for raw_seg in ptr.split("/")[1:]:
            seg = raw_seg.replace("~1", "/").replace("~0", "~")
            if isinstance(cur, dict) and seg in cur:
                cur = cur[seg]
            else:
                return None
        return cur if isinstance(cur, dict) else None
    except Exception:
        return None


def _deref(schema: Dict[str, Any], root: Dict[str, Any]) -> Dict[str, Any]:
    """Return a dereferenced schema if $ref present; otherwise original.

    Only supports internal fragment refs ('#/...').
    """
    if not isinstance(schema, dict):
        return schema
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref:
        target = _json_pointer_resolve(root, ref)
        if isinstance(target, dict):
            # Shallow-merge overlay (schema keywords besides $ref override target)
            if any(k for k in schema.keys() if k != "$ref"):
                merged = dict(target)
                for k, v in schema.items():
                    if k == "$ref":
                        continue
                    merged[k] = v
                return merged
            return target
    return schema


def _build_prompt(
    var_path: str,
    var_type: str,
    desc: Optional[str],
    list_hint: Optional[str] = None,
    enum_vals: Optional[List[Any]] = None,
    schema: Optional[Dict[str, Any]] = None,
) -> str:
    info = f" for '{var_path}'"
    if desc:
        info += f" (description: {desc})"
    if enum_vals:
        choices = ", ".join(str(v) for v in enum_vals[:8]) + (" ..." if len(enum_vals) > 8 else "")
        return f" Choose a value{info} from: {choices}. "
    if var_type == "boolean":
        # No explicit newline terminator for boolean; ChoicesStrat completes it.
        return f" Generate a boolean value{info}. It must be exactly one of: true, false. "
    if var_type in ("integer", "number"):
        parts: List[str] = []
        parts.append(
            f" Generate an integer{info}. {var_path}: " if var_type == "integer" else f" Generate a number{info}."
        )
        if isinstance(schema, dict):
            minimum = schema.get("minimum")
            maximum = schema.get("maximum")
            exclusive_min = schema.get("exclusiveMinimum")
            exclusive_max = schema.get("exclusiveMaximum")
            multiple_of = schema.get("multipleOf")
            constraints: List[str] = []
            # Bounds hint
            low = None
            high = None
            if isinstance(minimum, (int, float)):
                cmp = ">" if isinstance(exclusive_min, (int, float)) else "\u2265"
                low = f"{cmp} {minimum}"
            if isinstance(maximum, (int, float)):
                cmp = "<" if isinstance(exclusive_max, (int, float)) else "\u2264"
                high = f"{cmp} {maximum}"
            if low and high:
                constraints.append(f"between {minimum} and {maximum}")
            elif low:
                constraints.append(f"{low}")
            elif high:
                constraints.append(f"{high}")
            # multipleOf hint
            if isinstance(multiple_of, (int, float)) and multiple_of not in (0, 0.0):
                constraints.append(f"a multiple of {multiple_of}")
            if constraints:
                parts.append(" It should be " + " and ".join(constraints) + ".")
        parts.append(f" End the value with a newline. {var_path}: ")
        return "".join(parts)
    if var_type == "string":
        parts: List[str] = []
        parts.append(f" Generate a string{info}.")
        if isinstance(schema, dict):
            pat = schema.get("pattern")
            fmt = schema.get("format")
            constraints: List[str] = []
            if isinstance(pat, str) and pat:
                constraints.append(f"match this regular expression: /{pat}/")
            if isinstance(fmt, str) and fmt:
                constraints.append(f"be a valid {fmt}")
            if constraints:
                parts.append(" It should " + " and ".join(constraints) + ".")
        parts.append(f" End with a double quote. {var_path}: \"")
        return "".join(parts)
    if var_type == "object":
        parts: List[str] = []
        parts.append(f" Generate a JSON object{info}.")
        if isinstance(schema, dict):
            props = schema.get("properties")
            if isinstance(props, dict) and props:
                names = [k for k in props.keys() if isinstance(k, str)]
                if names:
                    sample = ", ".join(names[:5])
                    parts.append(f" It may contain keys such as: {sample}.")
        parts.append(f" End the value with a newline. {var_path}: ")
        return "".join(parts)
    if var_type == "array":
        hint = list_hint or "strings"
        return (
            f" Generate a JSON array of {hint}{info}. Use double quotes around each element and separate with ', '. "
            f"Close the list ']' and then emit a newline. "
        )
    return f" Generate a value{info}. "


def _make_strategy_for_field(field_schema: Dict[str, Any], *, root_schema: Dict[str, Any]) -> Tuple[Any, str]:
    """Return (strategy_ctor, normalized_type) for leaf field.

    Note: For arrays, this first version supports arrays of strings. Other
    element types may be added later.
    """
    field_schema = _deref(field_schema, root_schema)
    ftype = _type_of(field_schema) or "string"
    # const shortcut (scalars only for now)
    const_val = field_schema.get("const")
    if const_val is not None:
        def to_const_text(v: Any) -> str:
            if v is None:
                return "null"
            if isinstance(v, bool):
                return "true" if v else "false"
            return str(v)
        const_text = to_const_text(const_val)
        # Treat const as a single-choice enum; keep ftype so parsing still works.
        return ChoicesStrat([const_text]), ftype
    # Enum shortcut
    enum_vals = field_schema.get("enum")
    if isinstance(enum_vals, list) and enum_vals:
        # Choices must be strings; map JSON values to textual forms
        def to_choice(v: Any) -> str:
            if v is None:
                return "null"
            if isinstance(v, bool):
                return "true" if v else "false"
            return str(v)
        choices = [to_choice(v) for v in enum_vals]
        return ChoicesStrat(choices), ftype
    if ftype == "boolean":
        return ChoicesStrat(["true", "false"]), "boolean"
    if ftype == "integer":
        return CharsStrat(CharsMode.NUMERIC, stop="\n", min=1), ftype
    if ftype == "number":
        # Support full JSON/JS float format: optional leading '-', digits, optional decimal, optional exponent
        return CharsStrat(CharsMode.JS_FLOAT, stop="\n", min=1), ftype
    if ftype == "string":
        # STRING; newline terminator; use pattern/format-aware strategies when possible
        min_len = field_schema.get("minLength")
        pattern = field_schema.get("pattern")
        fmt = field_schema.get("format")

        # If no explicit pattern but a well-known format is present, synthesize a pattern.
        if not isinstance(pattern, str) or not pattern:
            if fmt == "date":
                # RFC 3339 full-date: YYYY-MM-DD (we ignore leap-year semantics here)
                pattern = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
            elif fmt == "date-time":
                # Very strict RFC 3339 subset: YYYY-MM-DDThh:mm:ssZ
                pattern = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
            elif fmt == "email":
                # Simplified email pattern (not fully RFC5321/5322-compliant)
                pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

        if isinstance(pattern, str) and pattern:
            return PatternStrat(
                pattern=pattern,
                stop="\"",
                min_chars=int(min_len) if isinstance(min_len, int) else 0,
            ), "string"

        return CharsStrat(
            CharsMode.STRING,
            stop="\"",
            min=int(min_len) if isinstance(min_len, int) else 0,
        ), "string"
    if ftype == "object":
        # Objects with no explicit properties (or open schemas) are treated as raw JSON
        # object text and parsed at assignment time.
        return CharsStrat(CharsMode.STRING, stop="\n", min=1), "object"
    if ftype == "array":
        # Note: full array semantics (prefixItems/items/contains) are implemented at the
        # flow level; here we only need a generic element strategy when using ListStrat.
        items = field_schema.get("items") or {}
        if isinstance(items, dict):
            items = _deref(items, root_schema)
        itype = _type_of(items) or "string"
        if itype == "string":
            min_items = field_schema.get("minItems")
            max_items = field_schema.get("maxItems")
            elem_min = items.get("minLength") if isinstance(items, dict) else None
            elem_strat = CharsStrat(
                CharsMode.STRING,
                stop='"',
                min=int(elem_min) if isinstance(elem_min, int) else 0,
            )
            list_strat = ListStrat(
                elements=elem_strat,
                open="[",
                close="]",
                wrap='"',
                sep=", ",
                min=int(min_items) if isinstance(min_items, int) else None,
                max=int(max_items) if isinstance(max_items, int) else None,
                end_with="\n",
            )
            return list_strat, "array"
        # Fallback (unsupported array element types): treat as string (JSON text)
        return CharsStrat(CharsMode.STRING, stop="\n"), "string"
    # Default fallback
    return CharsStrat(CharsMode.STRING, stop="\n"), "string"


def _assign_null_and_return_next(state: AppState, path: List[str], next_spec: Any) -> Any:
    _assign_parsed_value(state, path, "null", "null", None)
    return next_spec


def _assign_parsed_value(
    state: AppState,
    path: List[str],
    ftype: str,
    raw: Optional[str],
    schema: Optional[Dict[str, Any]] = None,
) -> None:
    logger.debug("assigning parsed value - path: %s, ftype: %s, raw: %s", path, ftype, raw)
    if raw is None:
        return
    text = (raw or "").strip()
    try:
        # Special-case literal "null" regardless of ftype
        if text.lower() == "null":
            val = None
        elif ftype == "null":
            val = None
        elif ftype == "boolean":
            val = True if text.lower() == "true" else False
        elif ftype == "integer":
            val = int(text)
        elif ftype == "number":
            val = float(text)
        elif ftype == "array":
            # Expect a JSON array string; best-effort parse
            val = json.loads(text)
        elif ftype == "object":
            # Expect a JSON object string; best-effort parse
            val = json.loads(text)
        else:  # string
            val = text
    except Exception:
        # On parse error, store raw
        val = text
    # Apply numeric constraints (minimum/maximum/exclusive*/multipleOf) best-effort
    try:
        if schema is not None and isinstance(schema, dict) and val is not None:
            if ftype in ("integer", "number") and isinstance(val, (int, float)):
                is_int = ftype == "integer"
                num = float(val)
                minimum = schema.get("minimum")
                maximum = schema.get("maximum")
                exclusive_min = schema.get("exclusiveMinimum")
                exclusive_max = schema.get("exclusiveMaximum")
                multiple_of = schema.get("multipleOf")

                # Minimum / exclusiveMinimum
                if isinstance(minimum, (int, float)):
                    minv = float(minimum)
                    if exclusive_min:
                        if num <= minv:
                            num = minv + (1.0 if is_int else abs(float(multiple_of or 1e-6)))
                    else:
                        if num < minv:
                            num = minv

                # Maximum / exclusiveMaximum
                if isinstance(maximum, (int, float)):
                    maxv = float(maximum)
                    if exclusive_max:
                        if num >= maxv:
                            num = maxv - (1.0 if is_int else abs(float(multiple_of or 1e-6)))
                    else:
                        if num > maxv:
                            num = maxv

                # multipleOf
                if isinstance(multiple_of, (int, float)) and multiple_of not in (0, 0.0):
                    step = float(multiple_of)
                    # Snap to nearest multiple
                    num = round(num / step) * step

                if is_int:
                    val = int(round(num))
                else:
                    val = float(num)
            # Apply pattern/format checks for strings (best-effort; no repair).
            if ftype == "string" and isinstance(val, str):
                pat = schema.get("pattern")
                if isinstance(pat, str) and pat:
                    try:
                        # Prefer fullmatch for anchored patterns so we do not
                        # accept proper prefixes by accident.
                        if "^" in pat or "$" in pat:
                            matched = re.fullmatch(pat, val)
                        else:
                            matched = re.search(pat, val)
                    except Exception:
                        pass
                fmt = schema.get("format")
                if isinstance(fmt, str) and fmt:
                    try:
                        if fmt == "date":
                            from datetime import datetime
                            datetime.strptime(val, "%Y-%m-%d")
                        elif fmt == "date-time":
                            from datetime import datetime
                            # Accept a strict RFC 3339 subset: YYYY-MM-DDThh:mm:ssZ
                            datetime.strptime(val, "%Y-%m-%dT%H:%M:%SZ")
                        elif fmt == "email":
                            # Very simple email check; for generative purposes only.
                            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", val):
                                pass
                    except Exception:
                        # If format validation fails, we keep the value but note that schema was stricter.
                        pass
    except Exception:
        # On any failure, keep original val
        pass

    obj = state.data.setdefault("result", {})
    _set_nested(obj, path, val)


def _build_chain_for_schema(state: AppState, rid: str) -> Optional[FlowQuestion]:
    schemas = get_schemas() or []
    logger.debug("schemas: %s", schemas)
    if not isinstance(schemas, list) or not schemas:
        return None
    # Pick the first schema that looks object-like; fall back to the first dict.
    schema: Optional[Dict[str, Any]] = None
    for s in schemas:
        if isinstance(s, dict) and (_type_of(s) == "object" or "properties" in s):
            schema = s
            break
    if schema is None:
        schema = schemas[0] if isinstance(schemas[0], dict) else None
    if not isinstance(schema, dict):
        return None

    state.data["schema"] = schema
    # Resolve a root $ref if present for starting type
    start_schema = _deref(schema, schema)
    # If the root schema is unsatisfiable for this generator (e.g., requires
    # an enum over arrays/objects, or only unsatisfiable required branches),
    # surface an error instead of attempting generation.
    if not validate_field_is_sat(start_schema):
        def _emit_unsat_error(actions, st: AppState, tokenizer):
            # Assume emit_error is available on the action builder in this environment.
            return actions.emit_error("JSON schema has unsatisfiable required fields; generation aborted.")

        return route_tool(_emit_unsat_error)
    validate_field_is_sat(start_schema)
    # If the root schema is an anyOf/oneOf union (common when using a top-level
    # $ref to a union definition), build a branch selector and then delegate
    # into the appropriate branch schema.
    union = start_schema.get("anyOf") or start_schema.get("oneOf")
    if isinstance(union, list) and union:
        labels: List[str] = []
        raw_schemas: List[Dict[str, Any]] = []
        eff_schemas: List[Dict[str, Any]] = []
        for idx, alt in enumerate(union):
            if not isinstance(alt, dict):
                continue
            lbl = _describe_anyof_alt(start_schema, alt, root_schema=schema)
            if lbl in labels:
                lbl = f"{lbl}_{idx}"
            labels.append(lbl)
            alt_d = _deref(alt, schema)
            raw_schemas.append(alt_d)
            eff_schemas.append(_flatten_anyof_alt(start_schema, alt_d, root_schema=schema))

        sel = FlowQuestion(
            name=f"json_schema.{rid}.select_root",
            prompt=" Select a root shape from union (anyOf/oneOf): ",
            strategy=ChoicesStrat(labels),
            erase_mode=EraseMode.ALL,
        )

        for lbl, raw_alt, eff_alt in zip(labels, raw_schemas, eff_schemas):
            def branch_for_alt(st: AppState, a=raw_alt, eff=eff_alt):
                a = _deref(a, schema)
                # If the root branch is an explicit null, treat the whole value as null.
                if _type_of(a) == "null":
                    st.data["result"] = None
                    return _finalize_output(st)
                # Otherwise, delegate to field-chain/object-chain logic starting at root.
                ftype = _type_of(eff) or ("object" if isinstance(eff.get("properties"), dict) else None)
                if ftype == "object" and isinstance(eff.get("properties"), dict):
                    return _build_object_chain([], eff, rid, lambda s: _finalize_output(s), root_schema=schema)
                return _build_field_chain_required([], eff, rid, lambda s: _finalize_output(s), root_schema=schema)

            sel.on(lbl, branch_for_alt)
        return sel

    # If the dereferenced root schema is not an object with properties, we do not
    # yet support generating non-object top-level values; emit an empty object as
    # a best-effort placeholder.
    if (_type_of(start_schema) != "object") or not (start_schema.get("properties") or {}):
        return FlowQuestion(
            name=f"json_schema.{rid}.empty",
            prompt=" Generating empty object ",
            strategy=ChoicesStrat(["ok"]),
            erase_mode=EraseMode.ALL,
        ).then(lambda st: _finalize_output(st))

    # Build an object chain for the root schema, pass root for $ref resolution
    return _build_object_chain([], start_schema, rid, lambda st: _finalize_output(st), root_schema=schema)


def _finalize_output(st: AppState):
    import json

    result = st.data.get("result") or {}
    root_schema = st.data.get("schema")

    # Best-effort post-processing for array-level constraints like uniqueItems.
    if isinstance(root_schema, dict):
        try:
            _apply_array_post_constraints(root_schema, result, root_schema)
        except Exception:
            # Do not fail the whole mod on post-processing issues.
            pass

    try:
        logger.debug("result: %s", result)
        return route_output(json.dumps(result))
    except Exception:
        logger.debug("result failover: %s", result)
        return route_output(str(result))


def _apply_array_post_constraints(
    schema: Dict[str, Any], instance: Any, root_schema: Dict[str, Any]
) -> None:
    """Apply array-level post constraints like uniqueItems recursively.

    This runs on the in-memory result object right before emitting JSON. It is
    best-effort and only mutates instance; it never raises.
    """
    schema = _deref(schema, root_schema)
    stype = _type_of(schema)

    # Handle arrays
    if stype == "array" and isinstance(instance, list):
        # uniqueItems: drop later duplicates, keeping first occurrences.
        if schema.get("uniqueItems"):
            seen: set[str] = set()
            dedup: list[Any] = []
            for el in instance:
                try:
                    key = json.dumps(el, sort_keys=True, separators=(",", ":"))
                except Exception:
                    key = repr(el)
                if key in seen:
                    continue
                seen.add(key)
                dedup.append(el)
            instance[:] = dedup

        # Recurse into elements using prefixItems/items schemas for guidance.
        prefix = schema.get("prefixItems") or []
        prefix = prefix if isinstance(prefix, list) else []
        items_schema = schema.get("items") or {}
        if isinstance(items_schema, dict):
            items_schema = _deref(items_schema, root_schema)

        for idx, el in enumerate(instance):
            if 0 <= idx < len(prefix) and isinstance(prefix[idx], dict):
                eschema = prefix[idx]
            else:
                eschema = items_schema if isinstance(items_schema, dict) else {}
            if isinstance(eschema, dict):
                _apply_array_post_constraints(eschema, el, root_schema)
        return

    # Handle objects: recurse into properties where we have schemas.
    if stype == "object" and isinstance(instance, dict):
        props: Dict[str, Any] = schema.get("properties", {}) or {}
        for key, subschema in props.items():
            if key in instance and isinstance(subschema, dict):
                _apply_array_post_constraints(subschema, instance[key], root_schema)
        return


def _build_object_chain(
    base_path: List[str], obj_schema: Dict[str, Any], rid: str, next_target: Callable[[AppState], Any], *, root_schema: Optional[Dict[str, Any]] = None
) -> FlowQuestion:
    root = obj_schema
    # Use the root schema stored in state at runtime when dereferencing nested refs
    # The builder functions will pass concrete root explicitly when needed.
    props: Dict[str, Any] = obj_schema.get("properties", {}) or {}
    required = [p for p in (obj_schema.get("required") or []) if isinstance(p, str)]
    ordered: List[str] = list(dict.fromkeys(list(required) + list(props.keys())))

    # Build property chains from last to first so we can thread next_target.
    # Resolve $ref for each property value if present. If a required property
    # has no schema in `properties`, synthesize a generic schema so the field
    # is still generated. For optional properties that are clearly
    # unsatisfiable, we skip generation entirely.
    next_spec: Any = next_target
    for key in reversed(ordered):
        subs = props.get(key)
        if not isinstance(subs, dict):
            # Some schemas have required fields without a corresponding entry in
            # `properties`. In that case, synthesize a generic schema so the
            # field is still generated.
            if key in required:
                subs = {}
            else:
                continue
        if root_schema is not None:
            subs = _deref(subs, root_schema)
        is_req = key in required
        # Skip optional fields that are unsatisfiable; required unsatisfiable
        # fields should be detected earlier at the root and turned into an
        # error.
        if (not is_req) and (not validate_field_is_sat(subs)):
            continue
        next_spec = _build_field_chain(base_path + [key], subs, is_req, rid, next_spec, root_schema=root_schema or obj_schema)
    # next_spec now is the first question
    assert isinstance(next_spec, FlowQuestion)
    return next_spec


def _build_field_chain(
    path: List[str], field_schema: Dict[str, Any], required: bool, rid: str, next_target: Callable[[AppState], Any] | FlowQuestion, *, root_schema: Dict[str, Any]
) -> FlowQuestion:
    qname_path = _sanitize_qname(".".join(path))
    field_schema = _deref(field_schema, root_schema)
    any_of = field_schema.get("anyOf")
    anyof_has_null = False
    if isinstance(any_of, list):
        for alt in any_of:
            if isinstance(alt, dict) and _type_of(_deref(alt, root_schema)) == "null":
                anyof_has_null = True
                break
    gate_needed = (not required and not anyof_has_null) or _type_of(field_schema) == "null"

    def cont_required():
        return _build_field_chain_required(path, field_schema, rid, next_target, root_schema=root_schema)

    if gate_needed:
        gate_q = FlowQuestion(
            name=f"json_schema.{rid}.gate.{qname_path}",
            prompt=f" Should I provide a value for '{'.'.join(path)}' or set it to null? ",
            strategy=ChoicesStrat(["provide", "null"]),
            erase_mode=EraseMode.ALL,
        )
        # On null, assign None and continue to next
        def on_null(st: AppState):
            return _assign_null_and_return_next(st, path, next_target(st) if callable(next_target) else next_target)

        gate_q.on("null", on_null)
        gate_q.on("provide", lambda st: cont_required())
        return gate_q
    else:
        return cont_required()


def _label_for_schema(s: Dict[str, Any], *, root_schema: Dict[str, Any]) -> str:
    s = _deref(s, root_schema)
    t = _type_of(s)
    if isinstance(s.get("enum"), list):
        return "enum"
    if t == "array":
        items = (s or {}).get("items") or {}
        it = _type_of(items) or "any"
        return f"array[{it}]"
    if t:
        return t
    if isinstance(s.get("properties"), dict):
        return "object"
    return "unknown"


def _describe_anyof_alt(base_schema: Dict[str, Any], alt_schema: Dict[str, Any], *, root_schema: Dict[str, Any]) -> str:
    """Human-readable label for an anyOf alternative, biased toward properties/items."""
    base_schema = _deref(base_schema, root_schema)
    alt = _deref(alt_schema, root_schema)
    t = _type_of(alt)
    if t == "null":
        return "null"
    # Overlay on an object schema: alt only adds required keys, base holds properties.
    if t is None and isinstance(base_schema.get("properties"), dict) and isinstance(alt.get("required"), list):
        req = [r for r in alt.get("required") if isinstance(r, str)]
        if req:
            inner = ", ".join(req[:5])
            return f"object (extra required: [{inner}])"
    if t == "object" or isinstance(alt.get("properties"), dict):
        props = alt.get("properties") or {}
        if isinstance(props, dict) and props:
            names = [k for k in props.keys() if isinstance(k, str)]
            if names:
                inner = ", ".join(names[:5])
                return f"object with properties [{inner}]"
        return "object"
    if t == "array" or "items" in alt or "prefixItems" in alt:
        items = alt.get("items")
        item_t = _type_of(items) if isinstance(items, dict) else None
        if not item_t and isinstance(base_schema.get("items"), dict):
            item_t = _type_of(base_schema["items"])
        if item_t:
            return f"array[{item_t}]"
        return "array"
    return _label_for_schema(alt, root_schema=root_schema)


def _flatten_anyof_alt(base_schema: Dict[str, Any], alt_schema: Dict[str, Any], *, root_schema: Dict[str, Any]) -> Dict[str, Any]:
    """Approximate flattening of a local alt with global constraints.

    - For object alts: merge global and local properties/required.
    - For array alts: merge global and local items/prefixItems and array keywords.
    - For other alts: return alt as-is (with dereferencing).
    """
    base = _deref(base_schema, root_schema)
    alt = _deref(alt_schema, root_schema)
    base_t = _type_of(base)
    t = _type_of(alt)
    eff_t = t or base_t

    # Object branch: merge properties/required. Also handle overlays where the
    # alternative does not declare a type but the base is an object (common
    # for anyOf/oneOf branches that only add extra `required` keys).
    if eff_t == "object" or isinstance(alt.get("properties"), dict):
        merged: Dict[str, Any] = dict(alt)
        base_props = base.get("properties") if isinstance(base.get("properties"), dict) else {}
        alt_props = alt.get("properties") if isinstance(alt.get("properties"), dict) else {}
        props_merged: Dict[str, Any] = {}
        if isinstance(base_props, dict):
            props_merged.update(base_props)
        if isinstance(alt_props, dict):
            props_merged.update(alt_props)
        if props_merged:
            merged["properties"] = props_merged
        base_req = base.get("required") if isinstance(base.get("required"), list) else []
        alt_req = alt.get("required") if isinstance(alt.get("required"), list) else []
        req_merged: List[str] = []
        for name in list(base_req) + list(alt_req):
            if isinstance(name, str) and name not in req_merged:
                req_merged.append(name)
        if req_merged:
            merged["required"] = req_merged
        merged["type"] = "object"
        return merged

    # Array branch: merge items/prefixItems and array-level constraints.
    if t == "array" or "items" in alt or "prefixItems" in alt:
        merged = dict(alt)
        if "items" not in merged and "items" in base:
            merged["items"] = base["items"]
        if "prefixItems" not in merged and "prefixItems" in base:
            merged["prefixItems"] = base["prefixItems"]
        for key in ("uniqueItems", "_uniqueItems", "minItems", "maxItems", "contains", "minContains", "maxContains"):
            if key not in merged and key in base:
                merged[key] = base[key]
        merged["type"] = "array"
        return merged

    # Fallback: keep alt as-is (with dereferencing).
    return dict(alt)


def _build_field_chain_required(
    path: List[str], field_schema: Dict[str, Any], rid: str, next_target: Callable[[AppState], Any] | FlowQuestion, *, root_schema: Dict[str, Any]
) -> FlowQuestion:
    qname_path = _sanitize_qname(".".join(path))
    # anyOf support
    field_schema = _deref(field_schema, root_schema)
    any_of = field_schema.get("anyOf")
    if isinstance(any_of, list) and any_of:
        labels: List[str] = []
        raw_schemas: List[Dict[str, Any]] = []
        eff_schemas: List[Dict[str, Any]] = []
        for idx, alt in enumerate(any_of):
            if not isinstance(alt, dict):
                continue
            alt_d = _deref(alt, root_schema)
            # Skip branches that are unsatisfiable for this generator.
            if not validate_field_is_sat(alt_d):
                continue
            lbl = _describe_anyof_alt(field_schema, alt, root_schema=root_schema)
            # Ensure uniqueness
            if lbl in labels:
                lbl = f"{lbl}_{idx}"
            labels.append(lbl)
            raw_schemas.append(alt_d)
            eff_schemas.append(_flatten_anyof_alt(field_schema, alt_d, root_schema=root_schema))
        if labels:
            sel = FlowQuestion(
                name=f"json_schema.{rid}.select_anyof.{qname_path}",
                prompt=f" Select an anyOf branch for '{'.'.join(path)}': ",
                strategy=ChoicesStrat(labels),
                erase_mode=EraseMode.ALL,
            )
            for lbl, raw_alt, eff_alt in zip(labels, raw_schemas, eff_schemas):
                def branch_for_alt(st: AppState, a=raw_alt, eff=eff_alt):
                    # If chosen alt is explicit null
                    a = _deref(a, root_schema)
                    if _type_of(a) == "null":
                        return _assign_null_and_return_next(st, path, next_target(st) if callable(next_target) else next_target)
                    # Otherwise continue with the flattened alt schema
                    return _build_field_chain_required(path, eff, rid, next_target, root_schema=root_schema)

                sel.on(lbl, branch_for_alt)
            return sel

    ftype = _type_of(field_schema) or ("object" if isinstance(field_schema.get("properties"), dict) else None)
    if ftype == "object":
        props = field_schema.get("properties")
        additional = field_schema.get("additionalProperties")
        # If there are declared properties, build an object chain.
        if isinstance(props, dict) and props:
            return _build_object_chain(path, field_schema, rid, next_target, root_schema=root_schema)
        # Unstructured object without declared properties.
        # If additionalProperties is explicitly false, this effectively forces an empty object.
        if additional is False:
            def assign_empty(st: AppState, ans: Optional[str]):
                root = st.data.setdefault("result", {})
                _set_nested(root, path, {})
            empty_q = FlowQuestion(
                name=f"json_schema.{rid}.{qname_path}._empty_object",
                prompt=f" Generating empty object for '{'.'.join(path)}'. ",
                strategy=ChoicesStrat(["ok"]),
                erase_mode=EraseMode.ALL,
            ).assign(assign_empty)
            empty_q.then(lambda st: next_target(st) if callable(next_target) else next_target)
            return empty_q
        # Otherwise, let the user choose between an empty object and a generated JSON object value.
        gate_q = FlowQuestion(
            name=f"json_schema.{rid}.{qname_path}._object_shape",
            prompt=f" For object '{'.'.join(path)}', should it be an empty object '{{}}' or contain key/value pairs? ",
            strategy=ChoicesStrat(["empty", "non-empty"]),
            erase_mode=EraseMode.ALL,
        )

        def on_empty(st: AppState):
            root = st.data.setdefault("result", {})
            _set_nested(root, path, {})
            return next_target(st) if callable(next_target) else next_target

        def on_non_empty(st: AppState):
            desc = field_schema.get("description") if isinstance(field_schema, dict) else None
            strat, norm_t = _make_strategy_for_field(field_schema, root_schema=root_schema)
            prompt = _build_prompt(
                ".".join(path),
                "object",
                desc,
                None,
                enum_vals=None,
                schema=field_schema,
            )
            q = FlowQuestion(
                name=f"json_schema.{rid}.{qname_path}",
                prompt=prompt,
                strategy=strat,
                completion_text="",
                erase_mode=EraseMode.ALL,
            ).assign(lambda st2, ans, p=list(path), t=norm_t, s=field_schema: _assign_parsed_value(st2, p, t, ans, s))
            q.then(lambda st2: next_target(st2) if callable(next_target) else next_target)
            return q

        gate_q.on("empty", on_empty)
        gate_q.on("non-empty", on_non_empty)
        return gate_q
    if ftype == "array":
        # Array handling: ask for count, then generate each element per its schema,
        # honoring prefixItems (tuple semantics), items (tail semantics), and
        # approximately enforcing contains + minContains.
        prefix_items = field_schema.get("prefixItems") or []
        prefix_items = prefix_items if isinstance(prefix_items, list) else []
        items_schema = field_schema.get("items") or {}
        if isinstance(items_schema, dict):
            items_schema = _deref(items_schema, root_schema)
        contains_schema = field_schema.get("contains") or {}
        if isinstance(contains_schema, dict) and contains_schema:
            contains_schema = _deref(contains_schema, root_schema)
        else:
            contains_schema = None
        qname_path = _sanitize_qname(".".join(path))
        count_qname = f"json_schema.{rid}.{qname_path}._count"
        min_items = field_schema.get("minItems")
        max_items = field_schema.get("maxItems")
        min_contains = field_schema.get("minContains")
        max_contains = field_schema.get("maxContains")

        def assign_init_list(st: AppState, ans: Optional[str]):
            # Initialize an empty list at the target path; elements will be assigned later
            root = st.data.setdefault("result", {})
            _set_nested(root, path, [])

        count_q = FlowQuestion(
            name=count_qname,
            prompt=f" How many elements should the array '{'.'.join(path)}' contain? End with a newline. ",
            strategy=CharsStrat(CharsMode.NUMERIC, stop="\n", min=1),
            erase_mode=EraseMode.ALL,
        ).assign(assign_init_list)

        def to_items_chain(st: AppState):
            raw = (st.answers.get(count_qname) or "").strip()
            logger.debug("raw answer: %s", raw)
            try:
                n = int(raw)
            except Exception:
                n = 0
            if isinstance(min_items, int):
                n = max(n, int(min_items))
            if isinstance(max_items, int):
                n = min(n, int(max_items))
            # Clamp minContains/maxContains to feasible range
            mc = int(min_contains) if isinstance(min_contains, int) else 0
            if n <= 0:
                mc = 0
            elif mc > n:
                mc = n
            # Currently we do not enforce maxContains strictly; treated as a soft hint.
            # Build per-item chain from last to first. We must not call
            # next_target(st) here, because that would eagerly invoke callbacks
            # like _finalize_output and capture stale state. Instead, we wrap it
            # in a function that will be executed only after all items have
            # been generated.
            def after_items(s: AppState, nt=next_target):
                return nt(s) if callable(nt) else nt

            next_spec: Any = after_items

            # Helper to assign a primitive element value after generation
            def item_assigner(idx: int, norm_t: str, schema_for_item: Optional[Dict[str, Any]]):
                logger.debug("item assigner, idx=%d, norm_t=%s, schema_for_item=%s", idx, norm_t, schema_for_item)
                return lambda st2, ans2, p=list(path) + [str(idx)], t=norm_t, s=schema_for_item: _assign_parsed_value(st2, p, t, ans2, s)

            for i in reversed(range(max(0, n))):
                ipath = path + [str(i)]
                # Choose schema for this index:
                #  - If contains+minContains is set, ensure the last `mc` indices use the contains schema.
                #  - Otherwise, use prefixItems[i] when present, else items_schema.
                if contains_schema is not None and mc > 0 and i >= n - mc:
                    idx_schema = contains_schema
                elif 0 <= i < len(prefix_items) and isinstance(prefix_items[i], dict):
                    idx_schema = _deref(prefix_items[i], root_schema)
                else:
                    idx_schema = items_schema if isinstance(items_schema, dict) else {}

                idx_type = _type_of(idx_schema) or ("object" if isinstance(idx_schema.get("properties"), dict) else "string") if isinstance(idx_schema, dict) else "string"

                if isinstance(idx_schema, dict) and idx_type == "object":
                    next_spec = _build_object_chain(
                        ipath,
                        idx_schema,
                        rid,
                        (lambda s, ns=next_spec: ns),
                        root_schema=root_schema,
                    )
                else:
                    # Leaf element (supports enum/items constraints)
                    desc = idx_schema.get("description") if isinstance(idx_schema, dict) else None
                    strat, norm_t = _make_strategy_for_field(idx_schema if isinstance(idx_schema, dict) else {}, root_schema=root_schema)
                    logger.debug("strategy: %s", strat)
                    enum_vals = idx_schema.get("enum") if isinstance(idx_schema, dict) else None
                    list_hint = None
                    prompt = _build_prompt(
                        ".".join(ipath),
                        norm_t,
                        desc,
                        list_hint,
                        enum_vals=enum_vals if isinstance(enum_vals, list) else None,
                        schema=idx_schema if isinstance(idx_schema, dict) else None,
                    )
                    elem_q = FlowQuestion(
                        name=f"json_schema.{rid}.{qname_path}._item_{i}",
                        prompt=prompt,
                        strategy=strat,
                        completion_text="",
                        erase_mode=EraseMode.ALL,
                    ).assign(item_assigner(i, norm_t, idx_schema if isinstance(idx_schema, dict) else None))
                    # Chain to next_spec
                    elem_q.then(lambda s, ns=next_spec: ns)
                    next_spec = elem_q
            return next_spec

        return count_q.then(lambda st: to_items_chain(st))

    # leaf
    desc = field_schema.get("description") if isinstance(field_schema, dict) else None
    strat, norm_t = _make_strategy_for_field(field_schema, root_schema=root_schema)
    logger.debug("strategy: %s", strat)
    list_hint = None
    if _type_of(field_schema) == "array":
        items = (field_schema or {}).get("items") or {}
        if isinstance(items, dict):
            items = _deref(items, root_schema)
        list_hint = (_type_of(items) or "strings") + " (quoted)"
    enum_vals = field_schema.get("enum") if isinstance(field_schema, dict) else None
    prompt = _build_prompt(
        ".".join(path),
        _type_of(field_schema) or norm_t,
        desc,
        list_hint,
        enum_vals=enum_vals if isinstance(enum_vals, list) else None,
        schema=field_schema if isinstance(field_schema, dict) else None,
    )

    q = FlowQuestion(
        name=f"json_schema.{rid}.{qname_path}",
        prompt=prompt,
        strategy=strat,
        completion_text="",
        erase_mode=EraseMode.ALL,
    ).assign(lambda st, ans, p=list(path), t=norm_t, s=field_schema: _assign_parsed_value(st, p, t, ans, s))
    # Then continue to next target
    q.then(lambda st: next_target(st) if callable(next_target) else next_target)
    return q


# Entry question dynamically builds the schema chain, then routes to it
def _entry_then(state: AppState):
    rid = state.request_id
    q = _build_chain_for_schema(state, rid)
    logger.debug("build chain for schema: %s", q)
    # If no schema was available, emit a helpful message
    if q is None:
        logger.debug("empty output - no schema available")
        return route_output("{}")
    return q


ENTRY = FlowQuestion(
    name="json_schema.entry",
    prompt=" Initialize JSON schema generation ",
    strategy=ChoicesStrat(["go"]),
    erase_mode=EraseMode.ALL,
).with_auto_answer(lambda st: "go").then(lambda st: _entry_then(st))


ENGINE = FlowEngine(
    entry_question=ENTRY,
    state_factory=lambda rid: AppState(request_id=rid),
)

import json
@mod
def json_schema_mod(event, actions, tokenizer):
    had_state = ENGINE._states.get(event.request_id) is not None
    if not had_state:
        schemas = get_schemas() or []
        if not isinstance(schemas, list) or not schemas:
            return None
        # Pick the first schema that looks object-like; fall back to the first dict.
        schema: Optional[Dict[str, Any]] = None
        for s in schemas:
            if isinstance(s, dict) and (_type_of(s) == "object" or "properties" in s):
                schema = s
                break
        if schema is None:
            schema = schemas[0] if isinstance(schemas[0], dict) else None
        if not isinstance(schema, dict):
            return None

        # Resolve a root $ref if present for starting type
        start_schema = _deref(schema, schema)
        # If the root schema is unsatisfiable for this generator (e.g., requires
        # an enum over arrays/objects, or only unsatisfiable required branches),
        # surface an error instead of attempting generation.
        if not validate_field_is_sat(start_schema):
            return actions.emit_error("JSON schema has unsatisfiable required fields; generation aborted.")

    if isinstance(event, Prefilled) and not had_state:
        return ENGINE.handle_event(event, actions, tokenizer)
    if isinstance(event, (ForwardPass, Added)):
        res = ENGINE.handle_event(event, actions, tokenizer)
        if isinstance(res, AdjustedLogits):
            if logger.isEnabledFor(logging.DEBUG):
                logprobs, indices = event.top_k_logprob(5)
                logger.debug("Top-k logprobs:")
                for k, (i, j) in enumerate(zip(*indices, *logprobs)):
                    logger.debug("    %d. %s (%d): %s", k, tokenizer.decode([i], add_special_tokens=False), i, j)
                logger.debug("Top-k adjusted logprobs:")
                logprobs, indices = res.top_k_logprob(5)
                for k, (i, j) in enumerate(zip(*indices, *logprobs)):
                    logger.debug("    %d. %s (%d): %s", k, tokenizer.decode([i], add_special_tokens=False), i, j)
        return res
    return actions.noop()
