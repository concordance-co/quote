---
name: concordance-mod
description: Create, upload, and debug Concordance mods for inference-time LLM interventions. Use when writing new mods, understanding mod patterns, uploading via CLI, making API requests to specific mods, or debugging mod issues. Covers events (Prefilled, ForwardPass, Sampled, Added), actions (noop, force_tokens, backtrack, adjust_logits, etc.), and advanced patterns like SelfPrompt and FlowEngine.
---

# Concordance Mod Development

Build inference-time interventions for LLMs using the Concordance system.

## Quick Reference

### Events (when your code runs)

| Event | When it fires | What you can access |
|-------|---------------|---------------------|
| `Prefilled` | Before first forward pass (fires at EVERY step!) | `context_info.tokens`, `request_id`, `step`, `max_steps` |
| `ForwardPass` | Before sampling, after logits computed | `logits`, `request_id`, `step` |
| `Sampled` | After sampling, before token added | `sampled_token`, `request_id`, `step` |
| `Added` | After token(s) added to context | `added_tokens`, `forced`, `request_id`, `tokens_so_far_len` |

### Actions (what you can do)

| Action | Valid Events | What it does |
|--------|--------------|--------------|
| `noop()` | All | Do nothing |
| `adjust_prefill(tokens, max_steps?)` | Prefilled only | Replace input tokens |
| `force_tokens(tokens)` | ForwardPass, Sampled, Added | Force specific tokens to be generated |
| `adjust_logits(logits, token_temp?)` | ForwardPass only | Modify probability distribution |
| `backtrack(n, tokens?)` | ForwardPass, Sampled, Added | Remove n tokens, optionally replace |
| `force_output(tokens)` | All | Skip remaining generation, finalize with tokens |
| `tool_calls(payload)` | All | Emit tool calls instead of text |

## Critical Gotchas

### 1. Prefilled fires EVERY step

The Prefilled event fires at the start of EVERY autoregressive step, not just once at the beginning. You MUST use an initialization guard:

```python
# WRONG - will re-initialize every step
@mod
def broken_mod(event, actions, tokenizer):
    if isinstance(event, Prefilled):
        # This runs on EVERY step!
        my_state[event.request_id] = {"value": 0}

# CORRECT - only initialize once
@mod
def working_mod(event, actions, tokenizer):
    if isinstance(event, Prefilled):
        if event.request_id not in my_state:  # Guard!
            my_state[event.request_id] = {"value": 0}
```

### 2. State must be keyed by request_id

The server handles multiple concurrent requests. Always key state by `event.request_id`:

```python
# WRONG - shared state between requests
accumulated_text = ""

# CORRECT - per-request state
accumulated_text: dict[str, str] = {}
```

### 3. Always use add_special_tokens=False

When encoding text for injection:

```python
# WRONG - may add BOS/EOS tokens
tokens = tokenizer.encode("Hello")

# CORRECT - raw tokens only
tokens = tokenizer.encode("Hello", add_special_tokens=False)
```

### 4. Use dataclasses for clean state

```python
from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class ModState:
    initialized: bool = False
    accumulated_tokens: List[int] = field(default_factory=list)
    step_count: int = 0

states: Dict[str, ModState] = {}

def get_state(rid: str) -> ModState:
    if rid not in states:
        states[rid] = ModState()
    return states[rid]
```

## Basic Mod Template

```python
from quote_mod_sdk import mod, Prefilled, ForwardPass, Added, Sampled
from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class State:
    initialized: bool = False
    # Add your state fields here

states: Dict[str, State] = {}

def get_state(rid: str) -> State:
    if rid not in states:
        states[rid] = State()
    return states[rid]

@mod
def my_mod(event, actions, tokenizer):
    """Brief description of what this mod does."""

    # Initialize on first Prefilled
    if isinstance(event, Prefilled):
        st = get_state(event.request_id)
        if not st.initialized:
            st.initialized = True
            # One-time setup here
        return actions.noop()

    # Handle ForwardPass (before sampling)
    if isinstance(event, ForwardPass):
        st = get_state(event.request_id)
        # Access event.logits, event.step
        return actions.noop()

    # Handle Sampled (after sampling, before adding)
    if isinstance(event, Sampled):
        st = get_state(event.request_id)
        # Access event.sampled_token
        return actions.noop()

    # Handle Added (after tokens added)
    if isinstance(event, Added):
        st = get_state(event.request_id)
        # Access event.added_tokens, event.forced
        return actions.noop()

    return actions.noop()
```

## Common Patterns

### Pattern 1: Token Injection at Generation Start

Force tokens at the beginning of generation:

```python
REASONING_PREFIX = "Let me think step by step.\n\n"

@mod
def inject_prefix(event, actions, tokenizer):
    if isinstance(event, Prefilled):
        if event.request_id not in states:
            states[event.request_id] = {"injected": False}
        return actions.noop()

    if isinstance(event, ForwardPass):
        st = states.get(event.request_id, {})
        if event.step == 0 and not st.get("injected", False):
            st["injected"] = True
            tokens = tokenizer.encode(REASONING_PREFIX, add_special_tokens=False)
            return actions.force_tokens(tokens)

    return actions.noop()
```

### Pattern 2: Word Replacement (Backtrack Pattern)

Watch for patterns and replace them:

```python
@dataclass
class State:
    initialized: bool = False
    accumulated_text: str = ""

states: Dict[str, State] = {}

@mod
def prevent_word(event, actions, tokenizer):
    if isinstance(event, Prefilled):
        if event.request_id not in states:
            states[event.request_id] = State(initialized=True)
        return actions.noop()

    if isinstance(event, Added):
        st = states.get(event.request_id)
        if st and not event.forced:
            text = tokenizer.decode(event.added_tokens)
            st.accumulated_text += text

            # Check for forbidden pattern
            if st.accumulated_text.endswith("bad phrase"):
                bad_tokens = tokenizer.encode("bad phrase", add_special_tokens=False)
                good_tokens = tokenizer.encode("good phrase", add_special_tokens=False)

                # Update state
                st.accumulated_text = st.accumulated_text[:-len("bad phrase")] + "good phrase"

                return actions.backtrack(len(bad_tokens), good_tokens)

    return actions.noop()
```

### Pattern 3: Logit Manipulation

Modify token probabilities:

```python
import numpy as np

@mod
def boost_token(event, actions, tokenizer):
    if isinstance(event, ForwardPass):
        # Get logits as numpy array
        logits = event.logits.to_numpy().copy()

        # Boost probability of specific token
        target_id = tokenizer.encode("Yes", add_special_tokens=False)[0]
        logits[0, target_id] += 5.0  # Add to logit

        # Or mask a token (make it impossible)
        banned_id = tokenizer.encode("No", add_special_tokens=False)[0]
        logits[0, banned_id] = float("-inf")

        return actions.adjust_logits(logits)

    return actions.noop()
```

### Pattern 4: Conditional Early Termination

End generation based on content:

```python
@mod
def stop_at_answer(event, actions, tokenizer):
    if isinstance(event, Prefilled):
        if event.request_id not in states:
            states[event.request_id] = {"text": ""}
        return actions.noop()

    if isinstance(event, Added):
        st = states.get(event.request_id)
        if st:
            st["text"] += tokenizer.decode(event.added_tokens)

            if "FINAL ANSWER:" in st["text"]:
                # Extract answer and force output
                answer = st["text"].split("FINAL ANSWER:")[-1].strip()
                tokens = tokenizer.encode(answer, add_special_tokens=False)
                return actions.force_output(tokens)

    return actions.noop()
```

### Pattern 5: Catch-and-Inject (Double-Check)

Detect a trigger phrase and inject additional content:

```python
CATCH = "Therefore, the answer is"
INJECTION = " Wait, let me double-check my reasoning first.\n\n"

@dataclass
class State:
    initialized: bool = False
    accumulated_text: str = ""
    caught: bool = False

states: Dict[str, State] = {}

@mod
def doublecheck(event, actions, tokenizer):
    if isinstance(event, Prefilled):
        if event.request_id not in states:
            states[event.request_id] = State(initialized=True)
        return actions.noop()

    if isinstance(event, Added):
        st = states.get(event.request_id)
        if st and not event.forced and not st.caught:
            text = tokenizer.decode(event.added_tokens)
            st.accumulated_text += text

            if st.accumulated_text.endswith(CATCH):
                st.caught = True
                catch_tokens = tokenizer.encode(CATCH, add_special_tokens=False)
                inject_tokens = tokenizer.encode(CATCH + INJECTION, add_special_tokens=False)
                return actions.backtrack(len(catch_tokens), inject_tokens)

    return actions.noop()
```

## Advanced: SelfPrompt

Constrained generation with automatic token masking. Useful for forcing the model to choose from specific options.

```python
from quote_mod_sdk import mod, Prefilled, ForwardPass, Added
from quote_mod_sdk.self_prompt import SelfPrompt, EraseMode
from quote_mod_sdk.strategies.strategy_constructor import (
    ChoicesStrat, UntilStrat, CharsStrat, ListStrat
)
from quote_mod_sdk.strategies.primitives import UntilEndType, CharsMode

# Create a constrained prompt
sp = SelfPrompt(
    prompt={"text": "The answer is: "},
    strategy=ChoicesStrat(["yes", "no", "maybe"]),
    completion="\n",
    erase=EraseMode.NONE,  # NONE | PROMPT | ALL
)

@mod
def constrained_choice(event, actions, tokenizer):
    if isinstance(event, Prefilled):
        sp.handle_prefilled(event, tokenizer)
        return actions.noop()

    if isinstance(event, ForwardPass):
        return sp.handle_forward_pass(event, actions, tokenizer)

    if isinstance(event, Added):
        sp.handle_added(event, actions, tokenizer)
        return actions.noop()

    return actions.noop()
```

### Strategy Types

| Strategy | Purpose | Example |
|----------|---------|---------|
| `ChoicesStrat` | Pick from finite options | `ChoicesStrat(["yes", "no", "unsure"])` |
| `UntilStrat` | Generate until delimiter | `UntilStrat("<start>", UntilEndType.TAG, "</end>")` |
| `CharsStrat` | Character class constraints | `CharsStrat(CharsMode.NUMERIC, stop=5)` |
| `ListStrat` | Generate lists | `ListStrat(elements=ChoicesStrat([...]), sep=", ")` |

### UntilStrat End Types

```python
# Until a closing tag
UntilStrat("<answer>", UntilEndType.TAG, "</answer>")

# Until newline
UntilStrat("", UntilEndType.NEWLINE, "\n")

# Until any character in set
UntilStrat("", UntilEndType.ANYCHAR, ".,!?\n")
```

### CharsStrat Modes

```python
# Exactly 4 digits
CharsStrat(CharsMode.NUMERIC, stop=4, min=4)

# Alphanumeric until dot
CharsStrat(CharsMode.ALPHANUMERIC, stop=".", min=2)
```

### Erase Modes

- `EraseMode.NONE` - Keep all generated tokens in output
- `EraseMode.PROMPT` - Erase the prompt, keep the answer
- `EraseMode.ALL` - Erase everything (hidden reasoning)

### Declarative SelfPrompt

For simpler cases, use the declarative helper:

```python
from quote_mod_sdk import self_prompt_mod

classifier = self_prompt_mod(
    prompt={"text": " Choose: A or B "},
    strategy=ChoicesStrat(["A", "B"]),
    completion={"suffix": "\n", "force": True},
)
```

## Advanced: FlowEngine

Multi-step constrained flows for complex interactions:

```python
from quote_mod_sdk.flow import (
    FlowQuestion, FlowEngine,
    route_question, route_message, route_summary, route_output
)
from quote_mod_sdk.strategies.strategy_constructor import ChoicesStrat, UntilStrat
from quote_mod_sdk.strategies.primitives import UntilEndType

# Define questions
q1 = FlowQuestion(
    name="sentiment",
    prompt="Sentiment analysis: ",
    strategy=ChoicesStrat(["positive", "negative", "neutral"]),
)

q2 = FlowQuestion(
    name="explanation",
    prompt="Brief explanation: ",
    strategy=UntilStrat("", UntilEndType.NEWLINE, "\n"),
)

# Chain them
q1.then(route_question(q2))
q2.then(route_message("Analysis complete."))

# Create engine
ENGINE = FlowEngine(entry_question=q1)

@mod
def sentiment_flow(event, actions, tokenizer):
    return ENGINE.handle_event(event, actions, tokenizer)
```

### Flow Routing Options

```python
# Route to next question
q1.then(route_question(q2))

# Route to message (ends flow)
q1.then(route_message("Done!"))

# Conditional routing based on answer
q1.on("yes", route_question(q_yes))
q1.on("no", route_question(q_no))

# Dynamic routing with lambda
q1.branch(lambda state: route_question(q2) if state.answers["q1"] == "yes" else route_message("Skipped"))

# Store custom data
q1.assign(lambda state, answer: setattr(state.data, "custom_key", answer))

# Force specific output
q1.then(route_output("Fixed response"))

# Generate summary
q1.then(route_summary())
```

### Accessing Flow State

```python
@mod
def flow_with_state(event, actions, tokenizer):
    output = ENGINE.handle_event(event, actions, tokenizer)

    # Access internal state
    state = ENGINE._get_state(event.request_id)
    answers = state.answers  # Dict of question name -> answer

    # Custom post-processing
    if answers.get("sentiment") == "negative":
        # Do something special
        pass

    return output
```

## CLI Commands

### Initialize a project

```bash
concai init
```

Creates:
- `.venv/` - Virtual environment with SDK
- Starter mod template at `mods/hello_world.py`
- `.env` with default configuration

### Upload a mod

**Single file:**
```bash
concai mod upload --file-name my_mod.py --url <server-url> --user-api-key <your-key>
```

**Directory (multiple files):**
```bash
concai mod upload --dir ./mods --url <server-url> --user-api-key <your-key>
```

Notes:
- File paths are auto-resolved under `mods/` with `.py` extension
- Directory mode requires exactly one `mod.py` entry file
- The function name decorated with `@mod` becomes the mod name

### Call a mod via API

```bash
curl -X POST <server-url>/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-User-Api-Key: <your-key>" \
  -d '{
    "model": "modularai/Llama-3.1-8B-Instruct-GGUF/my_mod",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

**Model string format:** `<base-model>/<mod-name>`

The base model must have at least 2 slash-separated segments, then append your mod name.

## Debugging Tips

### 1. Add print statements

Logs appear in server output:

```python
@mod
def debug_mod(event, actions, tokenizer):
    print(f"[DEBUG] Event: {type(event).__name__}, step: {getattr(event, 'step', 'N/A')}")
    print(f"[DEBUG] Request ID: {event.request_id}")

    if isinstance(event, Added):
        print(f"[DEBUG] Added tokens: {event.added_tokens}")
        print(f"[DEBUG] Decoded: {tokenizer.decode(event.added_tokens)}")
        print(f"[DEBUG] Forced: {event.forced}")

    return actions.noop()
```

### 2. Check event attributes

```python
if isinstance(event, ForwardPass):
    print(f"Logits shape: {event.logits.shape}")
    print(f"Step: {event.step}")

if isinstance(event, Prefilled):
    print(f"Max steps: {event.max_steps}")
    print(f"Tokens so far: {event.tokens_so_far_len}")
```

### 3. Verify state isolation

```python
@mod
def check_state(event, actions, tokenizer):
    if isinstance(event, Prefilled):
        print(f"Active requests: {list(states.keys())}")
        print(f"Current request: {event.request_id}")
    return actions.noop()
```

### 4. Common errors

| Error | Cause | Fix |
|-------|-------|-----|
| State bleeding between requests | Not keying by `request_id` | Use `states[event.request_id]` |
| Action runs every step | Missing initialization guard | Check `if not st.initialized` |
| Invalid action for event | Wrong event type | Verify action is valid for that event |
| Tokens not appearing | `add_special_tokens=True` | Use `add_special_tokens=False` |
| Mod not found | Wrong model string | Format: `base/model/mod_name` (3+ segments) |
| Backtrack not working | Wrong token count | Encode the exact text being replaced |

## SDK Imports Reference

```python
# Core
from quote_mod_sdk import mod, Prefilled, ForwardPass, Added, Sampled

# Conversation utilities
from quote_mod_sdk import get_conversation, set_conversation, clear_conversation

# Serialization
from quote_mod_sdk import serialize_mod

# SelfPrompt
from quote_mod_sdk.self_prompt import SelfPrompt, EraseMode
from quote_mod_sdk import self_prompt_mod

# Strategies
from quote_mod_sdk.strategies.strategy_constructor import (
    ChoicesStrat, UntilStrat, CharsStrat, ListStrat
)
from quote_mod_sdk.strategies.primitives import UntilEndType, CharsMode

# FlowEngine
from quote_mod_sdk.flow import (
    FlowQuestion, FlowDefinition, FlowEngine,
    route_question, route_message, route_summary, route_output, route_tool
)
```

## Complete Example: Reasoning Injection with Metrics

A production-ready mod that injects a reasoning prompt and tracks generation:

```python
"""Reasoning injection mod with progress tracking."""

from quote_mod_sdk import mod, Prefilled, ForwardPass, Added
from dataclasses import dataclass, field
from typing import Dict, List

REASONING_PROMPT = "Let me solve this step by step.\n\n"

@dataclass
class State:
    initialized: bool = False
    injected: bool = False
    accumulated_tokens: List[int] = field(default_factory=list)
    token_count: int = 0

states: Dict[str, State] = {}

def get_state(rid: str) -> State:
    if rid not in states:
        states[rid] = State()
    return states[rid]

@mod
def reasoning_injection(event, actions, tokenizer):
    """Injects reasoning prompt at generation start and tracks progress."""

    if isinstance(event, Prefilled):
        st = get_state(event.request_id)
        if not st.initialized:
            st.initialized = True
            print(f"[Reasoning] Initialized for {event.request_id}")
        return actions.noop()

    if isinstance(event, ForwardPass):
        st = get_state(event.request_id)

        # Inject on first step only
        if event.step == 0 and not st.injected:
            st.injected = True
            tokens = tokenizer.encode(REASONING_PROMPT, add_special_tokens=False)
            print(f"[Reasoning] Injecting {len(tokens)} tokens")
            return actions.force_tokens(tokens)

        return actions.noop()

    if isinstance(event, Added):
        st = get_state(event.request_id)

        # Track non-forced tokens
        if not event.forced:
            st.accumulated_tokens.extend(event.added_tokens)
            st.token_count += len(event.added_tokens)

            # Log progress every 50 tokens
            if st.token_count % 50 == 0:
                text = tokenizer.decode(st.accumulated_tokens[-100:])
                print(f"[Reasoning] {st.token_count} tokens generated")
                print(f"[Reasoning] Recent: ...{text[-80:]}")

        return actions.noop()

    return actions.noop()
```

## Complete Example: JSON Formatter with FlowEngine

Extract structured data using constrained generation:

```python
"""Extract title and story as JSON using FlowEngine."""

import json
from quote_mod_sdk import mod, Prefilled, ForwardPass, Added
from quote_mod_sdk.flow import FlowQuestion, FlowEngine, route_question
from quote_mod_sdk.strategies.strategy_constructor import UntilStrat
from quote_mod_sdk.strategies.primitives import UntilEndType

# Define extraction questions
q_title = FlowQuestion(
    name="title",
    prompt="Here is the title: <title>",
    strategy=UntilStrat("<title>", UntilEndType.TAG, "</title>"),
)

q_story = FlowQuestion(
    name="story",
    prompt="And now the story: <story>",
    strategy=UntilStrat("<story>", UntilEndType.TAG, "</story>"),
)

# Chain: title -> story
q_title.then(route_question(q_story))

ENGINE = FlowEngine(entry_question=q_title)

@mod
def json_formatter(event, actions, tokenizer):
    """Extracts title and story, outputs as JSON."""

    output = ENGINE.handle_event(event, actions, tokenizer)

    # Check if flow is complete
    state = ENGINE._get_state(event.request_id)
    title = state.answers.get("title")
    story = state.answers.get("story")

    if title and story:
        result = json.dumps({"title": title, "story": story}, indent=2)
        tokens = tokenizer.encode(result, add_special_tokens=False)
        return actions.force_output(tokens)

    return output
```
