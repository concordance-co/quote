Strategies package (simplified, SDK‑friendly)

This package provides a small, composable‑by‑nesting strategy system for constraining generation. It is intentionally simple, deterministic, and designed around the following principles:

- One root strategy per use case — no runtime composition/intersection.
- Human‑readable configuration with clear names and minimal knobs.
- Multi‑token wrappers/separators/end suffixes supported and consumed progressively.
- Deterministic token gating using precomputed token IDs/tries; decoding used sparingly.

Strategy types
- choices
  - fields: choices: list[str]
- until
  - fields: char: str
- chars
  - fields: kind: "alpha" | "alphanumeric" | "numeric", min: int = 0, max: int|null = null
- tokens
  - fields: items: list[str]  // each must encode to one token
- list
  - fields:
    - open: str|null
    - close: str|null
    - wrap: str|null
    - sep: str|null
    - end_with: str|null
    - min: int = 0
    - max: int|null = null
    - element: StrategySpec  // may itself be a list (nested lists supported)

List semantics (phases)
- in_open → await_element → in_wrap_open → in_element → in_wrap_close → await_sep → in_separator → in_close → in_end_with
- open/close/wrap/sep/end_with strings are tokenized into sequences and are consumed strictly in order.
- Element completion is determined by its nested strategy’s is_complete() result. When complete:
  - If wrap exists: close with wrap then go to await_sep; else go directly to await_sep. elements_completed increments in await_sep after wrap close (or immediately if no wrap).
- End: after consuming close, if end_with is provided the strategy will guide consumption of end_with tokens and then complete.

Compile API
- compile_strategy(spec: dict, tokenizer) -> Strategy
  - Validates and returns a Strategy instance with precomputed token ID sets/tries.

Runtime API
- Strategy.start(tokenizer) -> RuntimeState
- Strategy.allowed_tokens(state, tokenizer) -> set[int]
- Strategy.step(state, token_id, tokenizer) -> None
- Strategy.is_complete(state) -> bool

See compile.py, primitives.py and list_strategy.py for details and examples.

