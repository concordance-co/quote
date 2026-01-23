# JSON Schema Mod – Incremental Implementation Plan

This document is a living plan for bringing the JSON Schema–driven mod in `engine/examples/json_schema/mod.py` closer to full draft‑2020‑12 support, using Flow + SelfPrompt + strategies (including backtracking via `Backtrack` and `ForceTokens`).

After completing **any** step below, update:
- The step’s **Status** (Pending → In Progress → Done)
- Any notes/decisions that affect later steps

---

## Phase 0 – Baseline + Guardrails

**Step 0.1 – Capture current capabilities and constraints**  
Status: Pending  
Actions:
- Document the current behaviors of `json_schema_mod` (types, arrays/objects, anyOf, enums, refs) and which JSON Schema keywords are already partially handled.
- Explicitly list non‑goals for this iteration (e.g., no network fetch for external `$ref`, no full hyper‑schema support).

**Step 0.2 – Decide failure semantics & retry limits**  
Status: Pending  
Actions:
- Define global retry limits for per‑field backtracking (e.g., 3 attempts before giving up or relaxing).
- Decide what “giving up” means: fall back to a boundary value, drop the field, or surface a best‑effort value.
- Capture these rules here; they will be reused by many strategies.

---

## Phase 1 – Strategy Backtracking Interface

**Step 1.1 – Design an action‑aware Strategy interface**  
Status: Done  
Actions:
- Extend the strategy layer (see `engine/sdk/quote_mod_sdk/strategies/base.py`) with a *minimal* optional hook that allows the runtime to query for suggested actions after each `step`, e.g.:
  - “request_backtrack(n, reinject_tokens?)”
  - “force_tokens(tokens_to_force)”
- Keep the existing `Strategy` protocol backwards‑compatible; new strategies can implement the extended interface, old ones can ignore it.

**Step 1.2 – Wire strategy actions into SelfPrompt**  
Status: Done  
Actions:
- In `SelfPrompt.handle_added`, after each `compiled.step(...)`, check whether the strategy has requested a backtrack or forced tokens.
- If requested:
  - Populate `_State.backtrack_n` / `_State.backtrack_reinject` (for backtrack).
  - Or buffer `forced_tokens` so that `handle_forward_pass` can emit a `ForceTokens` action next.
- Ensure this integrates cleanly with existing erase modes and completion suffix handling.

**Step 1.3 – Add safety checks around backtracking**  
Status: Done  
Actions:
- Track per‑request and per‑field attempt counts in SelfPrompt state.
- If a strategy repeatedly requests backtracking beyond the configured limit, stop honoring further backtracks for that region and:
  - Mark the strategy as “give up” for this field, and
  - Let the mod choose a fallback (e.g., null or a simple constant).

---

## Phase 2 – Enhanced Scalar Strategies

**Step 2.1 – Refine numeric strategies with validation + backtrack**  
Status: Done  
Actions:
- For `integer` and `number` fields:
  - After a value is generated, parse it and enforce:
    - `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`
    - `multipleOf`
  - If constraints fail, use the action‑aware strategy to:
    - Request a full‑value backtrack, and
    - Optionally update internal hints (e.g., store “too small” / “too large”) to bias the next attempt.

**Step 2.2 – Add a regex‑aware string strategy for `pattern`**  
Status: Done  
Actions:
- Implement a `RegexStrat` (or extend an existing string strategy) that:
  - Uses the tokenizer + `decode_token` to maintain the current string.
  - Checks the target `pattern` (ECMA‑262 subset) on completion.
  - If the pattern fails, requests a full backtrack and adjusts prompt/hints.
- Initially support a practical subset of patterns (anchors, character classes, simple quantifiers); document unsupported constructs.

**Step 2.3 – Add format‑aware helpers for common `format` values**  
Status: Done  
Actions:
- For frequently used formats (e.g., `date-time`, `date`, `email`):
  - Implement helpers that generate canonical examples (e.g., “YYYY‑MM‑DD”).
  - Use them either as:
    - A dedicated strategy, or
    - A post‑generation validator that triggers backtrack + regeneration with a more specific prompt.
- Document which formats are supported and how strictly.

**Step 2.4 – Improve enum/const handling**  
Status: Done  
Actions:
- Ensure enum and const always use `ChoicesStrat` or forced tokens, including:
  - Top‑level fields
  - Array item `enum`
  - `anyOf` branches that are pure enums
- Make sure null enums (`enum: [null, ...]`) are mapped cleanly to “null” and parsed back to JSON null.

---

## Phase 3 – Array Semantics (uniqueItems, contains, prefixItems)

**Step 3.1 – Make prefixItems and items semantics explicit**  
Status: Done  
Actions:
- Update the array planning in `json_schema_mod.py` to:
  - Use `prefixItems` schemas for indices `< len(prefixItems)`.
  - Use `items` schema for indices `>= len(prefixItems)` (or all indices when `prefixItems` is absent).
- Ensure this is respected in both primitive and object arrays.

**Step 3.2 – Implement `uniqueItems` with repair via backtrack**  
Status: Done  
Actions:
- For arrays with `uniqueItems: true`:
  - After generating all elements, compare decoded values (scalars) or normalized signatures (objects).
  - When duplicates are found:
    - Backtrack from the first duplicate index to the end of the array.
    - For enums: adjust the element’s strategy to remove already used values from its choice set.
    - For other scalars: bias strategies away from exact repeats (e.g., via prompt hints or logit masks).
  - Limit the number of repair attempts; document behavior when uniqueness cannot be achieved.

**Step 3.3 – Implement `contains` + `minContains` (approximate `maxContains`)**  
Status: Done  
Actions:
- When `contains` is present:
  - Reserve at least `minContains` slots whose element strategies are specialized to satisfy the `contains` subschema.
  - Fill remaining slots with the general `items`/`prefixItems` behavior.
- After generation, count elements satisfying `contains`; if below `minContains`:
  - Backtrack some tail elements and regenerate them as satisfying items.
- Treat `maxContains` as a soft constraint (best effort), documenting the approximation.

---

## Phase 4 – Object Semantics (dependencies, patterns, extras)

**Step 4.1 – Tighten `required`, `properties`, and optional gates**  
Status: Pending  
Actions:
- Ensure required properties are always generated (or explicitly set to null when allowed).
- Keep the “provide or null” gate for optional properties, but:
  - Respect `anyOf` branches that already encode nullability.
  - Avoid double‑gating when an `anyOf` contains a `type: ["X", "null"]` branch.

**Step 4.2 – Implement `dependentSchemas` and `dependentRequired`**  
Status: Pending  
Actions:
- When a property P appears and has a `dependentSchemas` entry:
  - Merge its dependent schema into the object’s effective schema (similar to `allOf`) before building flows.
- For `dependentRequired` (from validation vocab):
  - After object generation, if P is present but required dependents are missing:
    - Either backtrack and regenerate the object, or
    - Backtrack just the missing properties and add them via new questions.

**Step 4.3 – Approximate `patternProperties` and `propertyNames`**  
Status: Pending  
Actions:
- For properties generated under `patternProperties`:
  - Use SelfPrompt to generate a property name and:
    - Check it against the regex or propertyNames schema.
    - If invalid, backtrack the property and resample the name.
- Start with simple patterns (prefixes, suffixes, basic character classes), and document limitations.

**Step 4.4 – Honor `additionalProperties` (no extras vs constrained extras)**  
Status: Pending  
Actions:
- For `additionalProperties: false`:
  - Do not generate any properties beyond those covered by `properties` and `patternProperties`.
- For `additionalProperties: { ...schema... }`:
  - Optionally allow a small number of extra properties:
    - Use property name generation + value strategies as above.
    - Validate them post‑generation and backtrack/repair if needed.

---

## Phase 5 – Composition & Logic (allOf, anyOf, oneOf, not, if/then/else)

**Step 5.1 – Schema normalization & simple allOf merging**  
Status: Pending  
Actions:
- Before building flows, normalize each location’s schema by:
  - Flattening simple `allOf` where possible.
  - Intersecting basic constraints: types, enums, numeric/string ranges.
  - Attaching `dependentSchemas` constraints to the object schema.
- Preserve the original subschemas for cases where merging is not straightforward.

**Step 5.2 – Robust anyOf/oneOf with branch‑level backtracking**  
Status: Pending  
Actions:
- For `anyOf`/`oneOf` at a given location:
  - Build a FlowQuestion to select a branch (using human‑readable labels derived from subschemas).
  - After generating under the chosen branch:
    - Run local constraint checks; if they fail, backtrack the value and try another branch.
  - For `oneOf`, optionally run quick post‑checks to detect “more than one matches” and log or adjust (best effort).

**Step 5.3 – Narrow `not` support with backtracking**  
Status: Pending  
Actions:
- Support a whitelisted set of `not` patterns, e.g.:
  - `{"not": {"enum": [...]}}`
  - `{"not": {"type": "null"}}`
- For these patterns:
  - After generating a candidate value, check the forbidden condition; if it matches, backtrack and resample with updated hints (e.g., exclude banned enum values).
- Document that general `not` is not fully supported.

**Step 5.4 – Approximate `if` / `then` / `else` behavior**  
Status: Pending  
Actions:
- During normalization, transform `if`/`then`/`else` into an internal branching representation, roughly:
  - Branch A: `if ∧ then`
  - Branch B: `¬if ∧ else`
- At generation time:
  - Try Branch A first, generate the value, then check whether `if` and `then` conditions hold.
  - If they do not, backtrack and attempt Branch B.
- Limit to patterns where `if` is reasonably cheap to evaluate (e.g., type or enum guards).

---

## Phase 6 – Integration, Testing, and Documentation

**Step 6.1 – Add unit and integration tests for strategies**  
Status: Pending  
Actions:
- Add tests under `engine/tests/sdk` (or equivalent) for:
  - New strategies (`RegexStrat`, enhanced numeric strategies, uniqueness helpers).
  - Backtracking behavior (ensure no infinite loops, correct Backtrack/ForceTokens usage).

**Step 6.2 – Add end‑to‑end tests for json_schema_mod**  
Status: Pending  
Actions:
- Construct small JSON Schemas covering:
  - Each new keyword/feature, one at a time.
  - Combinations (e.g., arrays with uniqueItems + minItems + contains).
- Verify that:
  - Generated JSON conforms to the schema using an external validator (where feasible).
  - The mod behaves reasonably when constraints are very tight or conflicting.

**Step 6.3 – Document supported JSON Schema subset and caveats**  
Status: Pending  
Actions:
- In this file and (optionally) a user‑facing doc, clearly list:
  - Keywords fully supported.
  - Keywords partially supported (approximate semantics).
  - Keywords ignored or out of scope (e.g., hyper‑schema, full unevaluated* semantics, external `$ref`).
- Provide guidance/examples for schema authors on how to write schemas that pair well with the mod.
