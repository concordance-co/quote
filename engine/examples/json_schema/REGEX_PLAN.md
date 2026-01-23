# JSON Schema `pattern` Support – Regex Strategy Plan

This document captures the **full context and detailed plan** for how we intend to support JSON Schema `pattern` in the Concordance JSON Schema mod, using the strategy + SelfPrompt framework. It’s meant to be read later without needing to re‑supply previous chat history.

The focus is on:

- The **JSON Schema regex subset** we care about.
- How that maps onto our **strategy engine** (`Strategy`, `SelfPrompt`).
- What is **already implemented** (date example, pattern wrapper, prompts, assignment‑time checks).
- A staged plan to build a **proper regex‑driven PatternStrategy** that drives `allowed_tokens` and uses backtracking only when needed.

---

## 0. Context: Where Regex Fits in the System

### 0.1 Strategy + SelfPrompt architecture

The Concordance SDK uses:

- A `Strategy` protocol (`engine/sdk/quote_mod_sdk/strategies/base.py`):
  - `start(tokenizer) -> RuntimeState`
  - `allowed_tokens(state, tokenizer) -> set[int]`
  - `disallowed_tokens(state, tokenizer) -> set[int]`
  - `step(state, token_id, tokenizer) -> Optional[Backtrack] | Optional[ForceTokens]`
  - `is_complete(state) -> bool`
  - `trim_answer(answer: str) -> str`

- `SelfPrompt` (`engine/sdk/quote_mod_sdk/self_prompt.py`):
  - For each `ForwardPass`:
    - Asks strategy for `allowed_tokens` / `disallowed_tokens`.
    - Masks logits accordingly.
  - For each `Added` event:
    - Feeds each `token_id` to `strategy.step(...)`.
    - Appends non‑forced tokens to `answer_tokens`.
    - If `step` returns `Backtrack` or `ForceTokens`, returns that action to the host.
  - Erase modes and completion suffixes are handled at this level.

### 0.2 Mod + JSON Schema layer

The JSON Schema mod (`engine/examples/json_schema/mod.py`):

- Inspects schemas returned by `get_schemas()`.
- Builds a flow of `FlowQuestion`s (`FlowEngine`) that:
  - For each property / array item / nested field:
    - Constructs a strategy via StrategyConstructors.
    - Wraps it in a `SelfPrompt` through `FlowEngine` / `SelfPrompt`.
  - Assigns the decoded answer into a nested `result` dict, applying numeric / array / object constraints before emitting JSON.

`pattern` lives at this layer:

- For string fields (and array items), we want:
  - Strategies that constrain generated strings to match the regex.
  - Optional repair via backtracking when a string violates the pattern (ideally as little as possible).

---

## 1. JSON Schema Regex Subset We Target

From the JSON Schema spec (recommended subset – *not* the entire ECMA‑262 suite):

- **Literals:**
  - A single Unicode character (other than reserved regex meta‑chars) matches itself.
- **Dot:**
  - `.` – any character except line break characters (newline handling may vary; for now treat as “any non‑newline char”).
- **Anchors:**
  - `^` – match at start of string.
  - `$` – match at end of string.
- **Grouping and alternation:**
  - `(...)` – group expressions.
  - `|` – alternation.
- **Character classes:**
  - `[abc]` – any of the listed chars.
  - `[a-z]` – ranges.
  - `[^abc]` – negated list.
  - `[^a-z]` – negated range.
- **Quantifiers:**
  - `+` – 1 or more.
  - `*` – 0 or more.
  - `?` – 0 or 1.
  - Lazy versions `+?`, `*?`, `??` – we can treat these as greedy for generation.
  - `{x}` – exactly x.
  - `{x,y}` – between x and y.
  - `{x,}` – at least x.
  - Non‑greedy forms `{x,y}?`, `{x,}?` – again can be treated effectively greedy for generative use.
- **Lookahead:**
  - `(?!x)`, `(?=x)` – negative/positive lookahead (allowed in subset, but we can *initially* disallow these and treat such patterns as unsupported for incremental enforcement; see below).
- **Escapes:**
  - Standard escapes like `\n`, `\r`, `\t`, etc. (plus doubled JSON escaping).

**Important design note:**  
We will **not** try to fully support all of this in the first iteration. Instead:

- Start with a **parse + NFA** design that can handle:
  - Literals, `.`, character classes, ranges, basic quantifiers, groups, alternation, `^`/`$`.
- Treat lookahead `(?=x)` / `(?!x)` as:
  - Either unsupported (pattern handled in “fallback mode” only), or
  - Ignored in the first pass (we can strip them, with a note that behavior differs from true semantics).

---

## 2. Current State of Pattern Support (Before Full Regex Engine)

### 2.1 Strategies in place

File: `engine/examples/json_schema/pattern_strategies.py`

- `PatternStrategy`:
  - Wraps `CharsStrategy(CharsMode.STRING, stop=..., min_chars=...)`.
  - Tracks decoded text in `_PatternState.text`.
  - Currently does **not** use the regex to restrict `allowed_tokens`; it relies on:
    - Strong prompts that mention `/pattern/`.
    - Assignment‑time regex validation as a safety net (in `_assign_parsed_value`).

- `PatternStrat` (StrategyConstructor):
  - For now:
    - If the pattern “looks like” a date pattern (`\d{4}-\d{2}-\d{2}`, `[0-9]{4}-[0-1][0-9]-[0-3][0-9]`, etc.), uses a **specialized** `DatePatternStrategy`.
    - Otherwise, uses `PatternStrategy`.

- `DatePatternStrategy`:
  - A concrete example of pattern → position‑based allowed characters → `allowed_tokens`.
  - Enforces fixed length (`YYYY-MM-DD`), digits and `-` only at certain positions.
  - Completes when 10 characters have been emitted; no backtracking needed if `allowed_tokens` is computed correctly.

### 2.2 Mod integration

File: `engine/examples/json_schema/mod.py`

- For string fields (`type == "string"`):
  - If `pattern` is present, uses `PatternStrat(pattern=..., stop='"', min_chars=minLength)`.
  - Otherwise, uses `CharsStrat(CharsMode.STRING, stop='"', min=...)`.
- Prompts:
  - `_build_prompt(...)` includes:
    - `It should match this regular expression: /<pattern>/`
    - `It should be a valid <format>` for `format` when present.
- Assignment:
  - `_assign_parsed_value(..., schema)`:
    - Runs `re.search(pattern, val)` as a best‑effort check, currently without repair (future backtracking hook point).

This means:

- We already **surface** `pattern` and `format` in prompts.
- We have a **pattern strategy** plugged into the SelfPrompt framework.
- We have one concrete example of **pattern‑driven `allowed_tokens`** (dates).

---

## 3. Target Design: Regex‑Driven PatternStrategy

We want `PatternStrategy` (or a richer successor) to:

- Take the JSON Schema `pattern` string.
- Parse it into an internal representation (AST).
- Build an NFA (or other automaton).
- Maintain a “current NFA state set” for the prefix generated so far.
- For each generation step:
  - Decide `allowed_tokens` by checking which tokens, if appended, keep the NFA in a viable state (non‑empty and still able to reach an accept).
- Only use `Backtrack` when **no tokens** can keep us in a viable state and we’re not yet complete.

### 3.1 Parsing Regex → AST

We will:

- Use Python’s `re` module **carefully**:
  - Not for matching, but to help parse, or we can implement a small custom parser (safer, more predictable).
- Build an AST with nodes like:
  - **Literal**: single character.
  - **Dot**: wildcard char.
  - **CharClass**: positive/negative `[abc]`, `[a-z]`, `[^...]`.
  - **Concat**: sequence of expressions.
  - **Alt**: alternation `A | B`.
  - **Group**: `(expr)` (just structural).
  - **Quantifier**: `Repeat(expr, min, max)` representing `*`, `+`, `?`, `{m}`, `{m,n}`, `{m,}`.
  - **Anchor**: `AnchorStart`, `AnchorEnd`.
  - **Lookahead** (optional later): we may initially **reject** patterns containing `(?` to avoid partial support.

Parsing requirements:

- Handle escape sequences: `\n`, `\r`, `\t`, `\\`, `\.` etc.
- Distinguish between literal `|`, `(`, `[`, etc., and structural tokens.
- Be robust against malformed patterns; fall back to “generic string strategy + assignment‑time check” when parsing fails.

### 3.2 AST → NFA

We will compile the AST into an NFA following a Thompson‑style construction:

- Each node emits a small NFA fragment with:
  - `start` state.
  - `End` (accept) state(s) and transitions labelled by:
    - A predicate on input chars (class, literal, dot).
    - Epsilon (ε) transitions for concat, alternation, grouping, and quantifiers.

Key semantics:

- `Concat(A, B)`:
  - Glue A’s accept states to B’s start with ε transitions.
- `Alt(A, B)`:
  - New start state → ε → A.start and B.start.
  - A.accept, B.accept → ε → new accept state.
- `Repeat(expr, min, max)`:
  - Finite bounds: unroll small ranges; or
  - For `*`, `+`, `{m,}`: standard NFA loops with ε transitions.
- Anchors:
  - For `^` and `$`, we interpret them as beginning/end of *the whole string*, so we effectively wrap patterns as if they were anchored. This simplifies generative semantics: we always want the entire generated string to match the `pattern`.

We also precompute:

- For each state, whether an accept state is reachable (graph search from accept states backwards). This is crucial for “prefix viability”: if no accept is reachable from a state set, we must avoid paths that lead uniquely there.

### 3.3 Runtime state: prefix NFA simulation

`PatternStrategy` will maintain:

- `current_states`: the ε‑closure of NFA states reachable after reading the current prefix.
- `text`: the decoded prefix string (mostly for debugging and possible assignment‑time checks).

At each `step` (Added token):

1. Decode the token to text `s`.
2. Simulate the NFA:
   - For each state in `current_states`, traverse transitions labelled with each char from `s`, computing a new set of states.
   - After processing full `s`, take ε‑closure.
3. If the resulting state set is empty:
   - Prefix cannot lead to any match anymore → we should have **avoided** this token by excluding it from `allowed_tokens`.
   - If we still reach this case (e.g., due to approximations or multi‑char tokens), we can:
     - Return a `Backtrack` for the entire field (or the last token), and reset `current_states` appropriately.
4. Otherwise, `current_states` is updated to the new state set.

Completion:

- `is_complete` should return `True` when:
  - There exists a state in `current_states` that is an accept state and we have reached an acceptable stop condition (e.g., stop token or length condition for certain patterns).
- For anchored patterns (our default), we want to ensure the **full** string is in an accept state at the end of generation.

### 3.4 `allowed_tokens` computation

Given `current_states` and a tokenizer, `allowed_tokens` will:

1. Iterate over candidate token IDs:
   - Decode each token to `s`.
   - Reject if `s` contains newline when pattern does not allow it (depending on dot semantics).
   - Simulate NFA over `s` from `current_states` to get `next_states`.
2. If `next_states` is empty → token is not viable; skip.
3. If `next_states` is non‑empty and contains at least one state from which an accept is reachable → token is viable; include in `allowed_tokens`.

Performance considerations:

- We can start with a simple implementation:
  - Use `require_token_ids(tokenizer)` to get all token IDs.
  - For each call to `allowed_tokens`, test each token.
- If this is too slow, we can optimize:
  - Cache `allowed_tokens` per `(NFA subset, position)` combination.
  - Preindex tokens by leading character, by membership in char classes, etc.
  - Short‑circuit tokens that clearly cannot match (e.g., those that contain characters outside the set of all possible pattern characters for any position).

### 3.5 Backtracking strategy

Because `allowed_tokens` uses NFA simulation, many invalid paths are avoided by construction. Backtracking is reserved for:

- **Edge cases**:
  - Multi‑char tokens that cause overshoots or subtle mismatches.
  - Complex patterns where our viability check is conservative and a dead end is discovered only after some steps.

Backtracking behavior:

- When `step` discovers that `current_states` is empty and no completion is possible:
  - It returns `Backtrack(n, tokens_to_reinject)`:
    - For a first version, we can backtrack the full answer for that field (`n = len(answer_tokens)`), and ask SelfPrompt to restart the entire field.
  - `SelfPrompt` already has a cap `_MAX_STRATEGY_BACKTRACK_ATTEMPTS` per SelfPrompt instance to avoid infinite loops.

---

## 4. Staged Implementation Plan (Regex Engine)

We intentionally stage this work to keep it manageable.

### Stage 1 – Tighten the current pattern infra

- Keep `PatternStrat` and `PatternStrategy` as the user‑facing API.
- Extend pattern prompts (already done) to explicitly mention `/pattern/`.
- Ensure assignment‑time `re.fullmatch` is used as a final validator:
  - If a generated string fails the regex, we at least **know**.
  - Optionally, we can trigger a **field‑level backtrack** here (e.g., mark a violation and have Flow regenerate that field).

Status: **Partially done** (pattern prompts + assignment checks in place).

### Stage 2 – Fixed‑length concatenations (prototype NFA)

Target subset:

- Patterns that are essentially concatenations of:
  - Literals, character classes, or dots, each with fixed quantifiers (`{n}`, `?`, no `*`/`+`/alternation).
  - Optional anchors `^`, `$`.

Implementation steps:

1. Build AST for this restricted subset.
2. Build NFA with fixed number of transitions.
3. Track an implicit “position” as in the date example, but driven by AST.
4. Implement `allowed_tokens` as:
   - “Does token text keep us aligned with allowed character classes for these positions?”
5. Integrate this into `PatternStrategy` as a special case when pattern analysis shows it’s fixed‑length and purely concatenative.

Stage 2 gives us:

- A generalization of the date pattern logic to any fixed‑length concatenation of classes/literals.

### Stage 3 – Add quantifiers, alternation, and grouping

Extend parser and NFA to handle:

- `*`, `+`, `?`, `{m,n}`, `{m,}`.
- Alternation `|`.
- Grouping `( ... )` including nested groups.

Implementation:

- Use Thompson construction for these features.
- Precompute reachability to accept states.
- Implement NFA simulation as described in 3.3–3.4.

At this stage:

- `PatternStrategy` becomes a true regex‑driven NFA strategy for the supported subset (without lookahead).

### Stage 4 – (Optional) Lookahead

Given the complexity and lower ROI for generative use, we can:

- Either:
  - Disallow patterns containing `(?` (reject incrementally, treat as fallback).
- Or:
  - Treat lookahead as advisory only, using assignment‑time `re` checks, but not enforcing them incrementally.

This keeps the incremental engine simpler while still supporting a large fraction of real‑world patterns.

---

## 5. Interaction With Formats

Although this document is about `pattern`, some patterns align closely with `format`:

- Example: `format: "date"` with `pattern: "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"`.
- Our parse → NFA engine can reuse knowledge from format‑specific strategies:
  - For `format: "date"` or `"date-time"`, we may embed extra semantic checks at assignment time (valid calendar dates), while still ensuring lexically correct patterns via `PatternStrategy`.

Plan for formats (high‑level):

- Short term:
  - Use prompts and assignment‑time validation for `format`.
- Mid‑term:
  - For a small set of formats (e.g. `date`, `date-time`, `email`), use either:
    - Pattern‑driven regex strategies (as described), or
    - Dedicated format strategies (similar to `DatePatternStrategy`) that also check semantics.

---

## 6. Summary

- We have:
  - A `PatternStrat` StrategyConstructor wired into the JSON Schema mod.
  - `PatternStrategy` and a concrete specialized `DatePatternStrategy` showing how to map a regex‑like pattern to `allowed_tokens` and per‑position constraints.
  - Prompts that explicitly mention `pattern` and `format`, and assignment‑time checks via Python `re`.

- We plan to:
  - Evolve `PatternStrategy` into a **real regex engine** for the JSON Schema subset (excluding lookahead at first) by:
    - Parsing the pattern into an AST.
    - Building an NFA for the AST.
    - Using NFA simulation to define `allowed_tokens` and determine when generation is complete.
    - Using backtracking only when necessary (dead ends), with SelfPrompt enforcing a per‑field backtrack cap.

- We will stage this work:
  - Start with fixed‑length concatenations (general case of the date pattern).
  - Gradually add quantifiers, alternation, and grouping.
  - Keep complicated lookahead constructs out of the incremental engine initially, relying on assignment‑time regex checks for those cases.

This plan is compatible with the JSON Schema spec’s recommended regex subset and fits into the existing flow + SelfPrompt + strategy architecture, minimizing backtracking while maximizing correctness for `pattern`‑constrained fields.

---

## 7. Reference File Paths

For future agents, these are the key files involved in regex/pattern handling and surrounding infrastructure:

- **Regex plan and pattern strategies**
  - `engine/examples/json_schema/REGEX_PLAN.md` – this document.
  - `engine/examples/json_schema/pattern_strategies.py` – `PatternStrategy`, `DatePatternStrategy`, and `PatternStrat`.

- **JSON Schema mod & flow wiring**
  - `engine/examples/json_schema/mod.py` – JSON Schema–driven mod:
    - Builds flows (`FlowQuestion`s) per schema.
    - Chooses strategies via `_make_strategy_for_field` (including `PatternStrat` for `pattern` strings).
    - Applies numeric, array, and pattern constraints at assignment time.
  - `engine/examples/json_schema/IMPLEMENTATION_PLAN.md` – broader implementation plan for the JSON Schema mod.

- **Strategy and SelfPrompt core**
  - `engine/sdk/quote_mod_sdk/strategies/base.py` – `Strategy` and `RuntimeState` protocols, `decode_token`, `require_token_ids`.
  - `engine/sdk/quote_mod_sdk/strategies/primitives.py` – `CharsStrategy`, `CharsMode` (STRING/ALPHANUMERIC/NUMERIC/JS_FLOAT), `ChoicesStrategy`, `UntilStrategy`, etc.
  - `engine/sdk/quote_mod_sdk/self_prompt.py` – `SelfPrompt` implementation:
    - Uses strategies per request.
    - Handles `allowed_tokens`/`disallowed_tokens`.
    - Emits `Backtrack` / `ForceTokens` actions (with a safety cap on strategy-driven backtracks).

- **Shared types / actions**
  - `engine/shared/src/shared/types.py` – event and action types:
    - `ModEvent`, `Prefilled`, `ForwardPass`, `Added`.
    - `ModAction`, `Backtrack`, `ForceTokens`, `AdjustedLogits`, etc.

These paths should give you all the relevant entry points to extend or debug regex/pattern behavior in this codebase.

