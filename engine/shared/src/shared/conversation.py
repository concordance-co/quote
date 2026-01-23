"""Utilities for storing per-request conversation metadata."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple
import copy
import json
import sys
from contextvars import ContextVar, Token


def _resolve_shared_state() -> tuple[
    Dict[str, List[Dict[str, Any]]], ContextVar[Optional[str]]
]:
    """Ensure conversation state is shared across module aliases."""

    existing = None
    for name in ("quote_mod_sdk.conversation", "sdk.quote_mod_sdk.conversation"):
        candidate = sys.modules.get(name)
        if candidate is not None and candidate is not sys.modules.get(__name__):
            existing = candidate
            break
    if existing is not None:
        convs = getattr(existing, "_CONVERSATIONS", None)
        ctx = getattr(existing, "_CURRENT_REQUEST_ID", None)
        if isinstance(convs, dict) and isinstance(ctx, ContextVar):
            return convs, ctx  # type: ignore[return-value]
    return {}, ContextVar("quote_sdk_current_request_id", default=None)


_CONVERSATIONS, _CURRENT_REQUEST_ID = _resolve_shared_state()
sys.modules.setdefault("quote_mod_sdk.conversation", sys.modules[__name__])
sys.modules.setdefault("sdk.quote_mod_sdk.conversation", sys.modules[__name__])


def set_schemas(request_id: str, schemas: Sequence[Dict[str, Any]]) -> None:
    """Persist a deep copy of the raw conversation messages for the request."""

    if not isinstance(request_id, str):
        raise TypeError("request_id must be a string")

    import pathlib
    import json

    t = pathlib.Path(f"/tmp/{request_id}_schemas").resolve()
    t.write_text(json.dumps(schemas))


def get_schemas(request_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return the stored messages for the active request.

    If ``request_id`` is provided it must match the current request context; otherwise
    ``PermissionError`` is raised. A deep copy of the conversation is returned.
    """
    active_request = _CURRENT_REQUEST_ID.get()
    if request_id is None:
        request_id = active_request
    elif request_id != active_request:
        raise PermissionError(
            "Access to another request's conversation is not permitted"
        )

    import pathlib
    import json

    if request_id is None:
        return []
    t = pathlib.Path(f"/tmp/{request_id}_schemas")
    schemas = json.loads(t.read_text())
    return copy.deepcopy(schemas) if schemas is not None else []


def set_conversation(request_id: str, messages: Sequence[Dict[str, Any]]) -> None:
    """Persist a deep copy of the raw conversation messages for the request."""

    if not isinstance(request_id, str):
        raise TypeError("request_id must be a string")

    import pathlib
    import json

    t = pathlib.Path(f"/tmp/{request_id}").resolve()
    t.write_text(json.dumps(messages))


def get_conversation(request_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return the stored messages for the active request.

    If ``request_id`` is provided it must match the current request context; otherwise
    ``PermissionError`` is raised. A deep copy of the conversation is returned.
    """
    active_request = _CURRENT_REQUEST_ID.get()
    if request_id is None:
        request_id = active_request
    elif request_id != active_request:
        raise PermissionError(
            "Access to another request's conversation is not permitted"
        )

    import pathlib
    import json

    if request_id is None:
        return []
    t = pathlib.Path(f"/tmp/{request_id}")
    messages = json.loads(t.read_text())
    return copy.deepcopy(messages) if messages is not None else []

def append_debug_logs(request_id: str, logs: str) -> None:
    if not isinstance(request_id, str):
        raise TypeError("request_id must be a string")

    with open(f"/tmp/logs_{request_id}", "a") as file:
        file.write(logs)

def read_debug_logs(request_id: str) -> str:
    if not isinstance(request_id, str):
        raise TypeError("request_id must be a string")

    import pathlib
    t = pathlib.Path(f"/tmp/logs_{request_id}")
    return t.read_text()


# --- Structured Mod Debug Traces ---


def init_mod_trace(request_id: str) -> None:
    """Initialize a new trace for a request."""
    if not isinstance(request_id, str):
        raise TypeError("request_id must be a string")

    import pathlib
    trace_path = pathlib.Path(f"/tmp/trace_{request_id}.json")
    # Initialize with empty list
    trace_path.write_text("[]")


def append_trace_event(
    request_id: str,
    event_type: str,
    step: int,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Append an event entry to the trace."""
    if not isinstance(request_id, str):
        raise TypeError("request_id must be a string")

    import pathlib
    trace_path = pathlib.Path(f"/tmp/trace_{request_id}.json")

    # Read existing trace
    if not trace_path.exists():
        init_mod_trace(request_id)

    trace_data = json.loads(trace_path.read_text())

    entry = {
        "type": "event",
        "event_type": event_type,
        "step": step,
        "details": details or {},
    }
    trace_data.append(entry)

    # Write back
    trace_path.write_text(json.dumps(trace_data))


def append_trace_mod_call(
    request_id: str,
    mod_name: str,
    event_type: str,
    step: int,
) -> None:
    """Append a mod call entry to the trace."""
    if not isinstance(request_id, str):
        raise TypeError("request_id must be a string")

    import pathlib
    trace_path = pathlib.Path(f"/tmp/trace_{request_id}.json")

    if not trace_path.exists():
        init_mod_trace(request_id)

    trace_data = json.loads(trace_path.read_text())

    entry = {
        "type": "mod_call",
        "mod_name": mod_name,
        "event_type": event_type,
        "step": step,
    }
    trace_data.append(entry)

    trace_path.write_text(json.dumps(trace_data))


def append_trace_mod_log(
    request_id: str,
    mod_name: str,
    log_message: str,
) -> None:
    """Append a mod log message to the trace."""
    if not isinstance(request_id, str):
        raise TypeError("request_id must be a string")

    import pathlib
    trace_path = pathlib.Path(f"/tmp/trace_{request_id}.json")

    if not trace_path.exists():
        init_mod_trace(request_id)

    trace_data = json.loads(trace_path.read_text())

    entry = {
        "type": "mod_log",
        "mod_name": mod_name,
        "message": log_message,
    }
    trace_data.append(entry)

    trace_path.write_text(json.dumps(trace_data))


def append_trace_action(
    request_id: str,
    action_type: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Append an action entry to the trace."""
    if not isinstance(request_id, str):
        raise TypeError("request_id must be a string")

    import pathlib
    trace_path = pathlib.Path(f"/tmp/trace_{request_id}.json")

    if not trace_path.exists():
        init_mod_trace(request_id)

    trace_data = json.loads(trace_path.read_text())

    entry = {
        "type": "action",
        "action_type": action_type,
        "details": details or {},
    }
    trace_data.append(entry)

    trace_path.write_text(json.dumps(trace_data))


def format_mod_trace(request_id: str, ansi_color: bool = False) -> str:
    """Format the mod trace for a request into a tree-like structure.

    Args:
        request_id: The request ID to format the trace for
        ansi_color: Whether to add ANSI color codes to the output
    """
    if not isinstance(request_id, str):
        raise TypeError("request_id must be a string")

    import pathlib
    trace_path = pathlib.Path(f"/tmp/trace_{request_id}.json")

    if not trace_path.exists():
        return ""

    try:
        trace = json.loads(trace_path.read_text())
    except Exception:
        return ""
    if not trace:
        return ""

    # ANSI color codes
    if ansi_color:
        RESET = "\033[0m"
        BOLD = "\033[1m"
        DIM = "\033[2m"
        CYAN = "\033[36m"
        GREEN = "\033[32m"
        YELLOW = "\033[33m"
        BLUE = "\033[34m"
        MAGENTA = "\033[35m"
        RED = "\033[31m"
    else:
        RESET = BOLD = DIM = CYAN = GREEN = YELLOW = BLUE = MAGENTA = RED = ""

    lines = []
    current_event_has_action = False
    pending_action = None

    def _truncate(text: str, max_len: int = 70) -> str:
        if len(text) <= max_len:
            return text
        return text[:max_len] + "..."

    def _wrap_log_line(text: str, max_width: int = 120, indent: str = "│             ") -> list[str]:
        """Wrap a log line to max_width, adding continuation indent for wrapped lines."""
        if len(text) <= max_width:
            return [text]

        result = []
        current_line = ""

        # Simple word-wrapping
        words = text.split()
        for word in words:
            if not current_line:
                test_line = word
            else:
                test_line = current_line + " " + word

            if len(test_line) <= max_width:
                current_line = test_line
            else:
                if current_line:
                    result.append(current_line)
                current_line = word

        if current_line:
            result.append(current_line)

        return result if result else [text]

    def _format_details(details: Dict[str, Any]) -> str:
        parts = []
        for key, value in details.items():
            if key == "input_text":
                parts.append(f'Input: "{_truncate(str(value)).replace("\n", "\\n")}"')
            elif key == "token_text":
                parts.append(f'Sampled: "{str(value).replace("\n", "\\n")}"')
            elif key == "prompt_length":
                parts.append(f"Init Prompt Length: {value}")
            elif key == "new_length":
                parts.append(f"new length: {value}")
            elif key == "top_tokens":
                # Format as [" a": 0.45, "\n": 0.23, "\t": 0.15]
                if isinstance(value, list):
                    token_strs = []
                    for item in value[:3]:
                        if isinstance(item, dict):
                            tok = item.get("token_str", "")
                            prob = item.get("prob", 0.0)
                            # Escape special characters for display
                            tok_escaped = tok.replace('\n', '\\n').replace('\t', '\\t').replace('\r', '\\r')
                            token_strs.append(f'"{tok_escaped}": {prob:.2f}')
                    if token_strs:
                        parts.append(f"top 3: [{', '.join(token_strs)}]")
            elif key == "tokens_preview":
                parts.append(f"tokens: {value}")
            elif key == "token_count":
                parts.append(f"{value} token(s)")
            elif key == "forced":
                if value:
                    parts.append("forced")
            elif key == "tokens" and isinstance(value, list):
                # Show token texts for Added event
                tokens_str = ", ".join(f'"{t}"' for t in value[:5])
                if len(value) > 5:
                    tokens_str += "..."
                parts.append(f"tokens: [{tokens_str}]")
            elif key == "error":
                parts.append(f'error: "{value}"')
            elif key == "logits_shape":
                parts.append(f"logits shape: {value}")
            elif key == "temperature":
                parts.append(f"temp: {value}")
            elif key == "has_tool_calls":
                if value:
                    parts.append("tool calls present")
            elif key == "max_steps":
                parts.append(f"max_steps: {value}")
            elif key == "n":
                parts.append(f"n: {value}")
            else:
                parts.append(f"{key}: {value}")
        return ", ".join(parts) if parts else ""

    i = 0
    while i < len(trace):
        entry = trace[i]
        entry_type = entry.get("type")

        if entry_type == "event":
            # Close previous event with action (or blank line)
            if pending_action:  # Check if truthy (not None and not empty string)
                lines.append(pending_action)
                pending_action = None

            event_type = entry.get("event_type", "")
            details = entry.get("details", {})
            details_str = _format_details(details)

            if details_str:
                lines.append(f"{CYAN}├──[{BOLD}{event_type}{RESET}{CYAN}]{RESET} {details_str}")
            else:
                lines.append(f"{CYAN}├──[{BOLD}{event_type}{RESET}{CYAN}]{RESET}")

            current_event_has_action = True

            # Look ahead for mod calls and logs
            j = i + 1
            mod_calls = []
            all_mod_logs = []
            action_entry = None

            while j < len(trace):
                next_entry = trace[j]
                next_type = next_entry.get("type")

                if next_type == "event":
                    break
                elif next_type == "mod_call":
                    mod_calls.append(next_entry)
                elif next_type == "mod_log":
                    message = next_entry.get("message", "")
                    mod_name = next_entry.get("mod_name", "")
                    # Keep the complete log message (may contain actual newlines)
                    if message.strip():
                        all_mod_logs.append((mod_name, message.strip()))
                elif next_type == "action":
                    action_entry = next_entry
                    break

                j += 1

            # Determine if we should show mod details
            # Show mods if: there are logs OR action is not Noop
            action_type = action_entry.get("action_type", "") if action_entry else "Noop"
            has_logs = len(all_mod_logs) > 0
            is_noop = action_type == "Noop"
            show_mod_details = has_logs or not is_noop

            if show_mod_details:
                # Output mod calls with their logs
                current_mod = None
                log_idx = 0

                for idx, mod_call in enumerate(mod_calls):
                    mod_name = mod_call.get("mod_name", "UnknownMod")
                    event_type_mod = mod_call.get("event_type", "")

                    # Find logs for this mod
                    mod_logs = [log for name, log in all_mod_logs if name == mod_name]

                    if mod_logs or not is_noop:
                        # Determine if this is the last mod and action is Noop
                        is_last_mod = (idx == len(mod_calls) - 1)
                        use_end_branch = is_last_mod and is_noop

                        # Output mod call
                        if use_end_branch:
                            lines.append(f"{DIM}│     {RESET}{GREEN}└─ {mod_name}{RESET}{DIM}({event_type_mod}){RESET}")
                            # Logs with more indentation (under └─)
                            for log_idx, log_line in enumerate(mod_logs):
                                prefix = "├" if log_idx < len(mod_logs) - 1 else "└"

                                # Handle multi-line logs (actual newlines in the log)
                                log_lines = log_line.splitlines()
                                if not log_lines:
                                    log_lines = [""]

                                # First line of this log entry
                                first_line = log_lines[0]
                                wrapped = _wrap_log_line(first_line, max_width=100)

                                # Output Logs: label
                                lines.append(f'{DIM}│           {prefix}{RESET} {YELLOW}Logs:{RESET}')

                                # Output first wrapped line (first line normal, continuations indented)
                                for idx, wrap_line in enumerate(wrapped):
                                    if idx == 0:
                                        lines.append(f'{DIM}│               {RESET}{wrap_line}')
                                    else:
                                        # Extra indent for wrapped continuation
                                        lines.append(f'{DIM}│                 {RESET}{wrap_line}')

                                # Output subsequent lines from actual newlines
                                for subsequent in log_lines[1:]:
                                    if subsequent:  # Skip empty lines
                                        wrapped_sub = _wrap_log_line(subsequent, max_width=100)
                                        for idx, wrap_line in enumerate(wrapped_sub):
                                            if idx == 0:
                                                lines.append(f'{DIM}│               {RESET}{wrap_line}')
                                            else:
                                                # Extra indent for wrapped continuation
                                                lines.append(f'{DIM}│                 {RESET}{wrap_line}')
                        else:
                            lines.append(f"{DIM}│     {RESET}{GREEN}├─ {mod_name}{RESET}{DIM}({event_type_mod}){RESET}")
                            # Logs with normal indentation
                            for log_idx, log_line in enumerate(mod_logs):
                                prefix = "├" if log_idx < len(mod_logs) - 1 else "└"

                                # Handle multi-line logs (actual newlines in the log)
                                log_lines = log_line.splitlines()
                                if not log_lines:
                                    log_lines = [""]

                                # First line of this log entry
                                first_line = log_lines[0]
                                wrapped = _wrap_log_line(first_line, max_width=100)

                                # Output Logs: label
                                lines.append(f'{DIM}│     │     {prefix}{RESET} {YELLOW}Logs:{RESET}')

                                # Output first wrapped line (first line normal, continuations indented)
                                for idx, wrap_line in enumerate(wrapped):
                                    if idx == 0:
                                        lines.append(f'{DIM}│     │         {RESET}{wrap_line}')
                                    else:
                                        # Extra indent for wrapped continuation
                                        lines.append(f'{DIM}│     │           {RESET}{wrap_line}')

                                # Output subsequent lines from actual newlines
                                for subsequent in log_lines[1:]:
                                    if subsequent:  # Skip empty lines
                                        wrapped_sub = _wrap_log_line(subsequent, max_width=100)
                                        for idx, wrap_line in enumerate(wrapped_sub):
                                            if idx == 0:
                                                lines.append(f'{DIM}│     │         {RESET}{wrap_line}')
                                            else:
                                                # Extra indent for wrapped continuation
                                                lines.append(f'{DIM}│     │           {RESET}{wrap_line}')

                # Output action (or blank line for Noop)
                if is_noop:
                    # For Noop, always just add a blank line with │
                    pending_action = f"{DIM}│{RESET}"
                elif action_entry:
                    # For real actions, show the action line
                    details = action_entry.get("details", {})
                    details_str = _format_details(details)

                    if details_str:
                        pending_action = f"{DIM}│   {RESET}{BLUE}<─┴{RESET} {MAGENTA}{action_type}{RESET}({details_str})"
                    else:
                        pending_action = f"{DIM}│   {RESET}{BLUE}<─┴{RESET} {MAGENTA}{action_type}{RESET}"
            else:
                # No mod details to show - don't output any action line
                pending_action = ""
                current_event_has_action = False

            # Skip all the entries we've processed
            i = j
            continue

        i += 1



    # Close the last event
    if pending_action:  # Check if truthy (not None and not empty string)
        lines.append(pending_action)

    if not lines:
        return ""

    return f"{BOLD}GenStart{RESET}\n" + "\n".join(lines) + f"\n{BOLD}Done{RESET}"


def get_mod_trace(request_id: str, ansi_color: bool = False) -> str:
    """Get the formatted mod trace for a request.

    Args:
        request_id: The request ID
        ansi_color: Whether to add ANSI color codes
    """
    return format_mod_trace(request_id, ansi_color=ansi_color)


def get_mod_trace_data(request_id: str) -> List[Dict[str, Any]]:
    """Get the raw trace data for a request as a JSON-serializable list.

    Returns the underlying trace data structure without formatting.
    Each entry is a dict with 'type' field indicating entry type:
    - {"type": "event", "event_type": str, "step": int, "details": dict}
    - {"type": "mod_call", "mod_name": str, "event_type": str, "step": int}
    - {"type": "mod_log", "mod_name": str, "message": str}
    - {"type": "action", "action_type": str, "details": dict}
    """
    if not isinstance(request_id, str):
        raise TypeError("request_id must be a string")

    import pathlib
    trace_path = pathlib.Path(f"/tmp/trace_{request_id}.json")

    if not trace_path.exists():
        return []

    try:
        trace_data = json.loads(trace_path.read_text())
        return trace_data
    except Exception as e:
        return []


def clear_mod_trace(request_id: str) -> None:
    """Clear the mod trace for a request."""
    if not isinstance(request_id, str):
        raise TypeError("request_id must be a string")

    import pathlib
    trace_path = pathlib.Path(f"/tmp/trace_{request_id}.json")

    if trace_path.exists():
        try:
            trace_path.unlink()
        except Exception:
            pass


def clear_conversation(request_id: str) -> None:
    """Remove cached messages for the given request id (if present)."""
    import os

    os.remove(f"/tmp/{request_id}")


def push_request_context(request_id: Optional[str]) -> Optional[Token]:
    """Set the current request context; returns a token for later reset."""

    if request_id is None:
        return None
    return _CURRENT_REQUEST_ID.set(request_id)


def pop_request_context(token: Optional[Token]) -> None:
    """Restore the previous request context."""

    if token is not None:
        _CURRENT_REQUEST_ID.reset(token)


__all__ = [
    "set_conversation",
    "get_conversation",
    "clear_conversation",
    "push_request_context",
    "pop_request_context",
    "tool_call_pairs",
    "init_mod_trace",
    "append_trace_event",
    "append_trace_mod_call",
    "append_trace_mod_log",
    "append_trace_action",
    "format_mod_trace",
    "get_mod_trace",
    "get_mod_trace_data",
    "clear_mod_trace",
]




def _stringify_tool_content(content: Any) -> Optional[str]:
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        fragments: List[str] = []
        for item in content:
            if isinstance(item, str):
                fragments.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    fragments.append(text)
                elif isinstance(item.get("content"), str):
                    fragments.append(item["content"])
            else:
                return None
        if fragments:
            return "".join(fragments)
        return None
    try:
        return json.dumps(content)
    except TypeError:
        return str(content)


def tool_call_pairs(
    messages: Optional[Sequence[Dict[str, Any]]] = None,
) -> List[Tuple[Dict[str, Any], Optional[str]]]:
    convo = list(messages) if messages is not None else get_conversation()
    pairs: List[Tuple[Dict[str, Any], Optional[str]]] = []
    index_by_id: Dict[str, int] = {}
    for message in convo:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role == "assistant":
            calls = message.get("tool_calls")
            if not isinstance(calls, list):
                continue
            for call in calls:
                if not isinstance(call, dict):
                    continue
                cid = call.get("id")
                if not isinstance(cid, str):
                    continue
                stored_call = copy.deepcopy(call)
                index_by_id[cid] = len(pairs)
                pairs.append((stored_call, None))
        elif role == "tool":
            call_id = message.get("tool_call_id")
            if not isinstance(call_id, str):
                continue
            idx = index_by_id.get(call_id)
            if idx is None:
                continue
            response = _stringify_tool_content(message.get("content"))
            call, _ = pairs[idx]
            pairs[idx] = (call, response)
    return pairs
