# Building Token Injection Mods for Coding Agents

A condensed guide to creating inference-time interventions using the Concordance Quote Mod SDK.

## Table of Contents
- [Core Concepts](#core-concepts)
- [The Prefill Problem](#the-prefill-problem)
- [Building Your First Mod](#building-your-first-mod)
- [Token Injection Patterns](#token-injection-patterns)
- [Uploading and Using Mods](#uploading-and-using-mods)
- [Advanced Patterns](#advanced-patterns)

---

## Core Concepts

### Events
Mods receive events at critical points during inference:

- **Prefilled** — Before first forward pass; access initial prompt tokens
- **ForwardPass** — Before sampling; access raw logits
- **Added** — After token(s) added to sequence (sampled or forced)

### Actions
Return actions to steer generation:

- `adjust_prefill(tokens)` — Replace input tokens before first pass
- `force_tokens(tokens)` — Force specific next tokens, skip sampling
- `adjust_logits(logits)` — Modify next-token probabilities (mask/bias)
- `backtrack(n, tokens?)` — Remove recent tokens, optionally replace
- `force_output(tokens)` — Skip all forward passes, finalize immediately
- `tool_calls(payload)` — Emit tool call instead of text
- `noop()` — Do nothing

### Basic Mod Structure

```python
from quote_mod_sdk import mod, Prefilled, ForwardPass, Added

@mod
def my_mod(event, actions, tokenizer):
    if isinstance(event, Prefilled):
        return actions.noop()
    if isinstance(event, ForwardPass):
        return actions.noop()
    if isinstance(event, Added):
        return actions.noop()
    return actions.noop()
```

---

## The Prefill Problem

**CRITICAL:** The `Prefilled` event fires at EVERY autoregressive step, not just once at initialization.

### Why This Happens
The inference engine re-evaluates the prefill context at each decoding step. Your mod receives a `Prefilled` event every time.

### The Solution: Initialization Guards

**Always use an initialization flag to ensure one-time setup:**

```python
from dataclasses import dataclass

@dataclass
class State:
    initialized: bool = False
    # ... other state

states: dict[str, State] = {}

def get_state(request_id: str) -> State:
    if request_id not in states:
        states[request_id] = State()
    return states[request_id]

@mod
def my_mod(event, actions, tokenizer):
    st = get_state(event.request_id)
    
    if isinstance(event, Prefilled):
        # Guard prevents re-running on every step
        if not st.initialized:
            st.initialized = True
            # ONE-TIME SETUP HERE
            prompt_text = tokenizer.decode(
                event.context_info.tokens[:event.context_info._prompt_len]
            )
            # Process prompt...
        return actions.noop()
```

### Common Mistake Example

```python
# ❌ WRONG - This runs at EVERY step!
@mod
def bad_prepend(event, actions, tokenizer):
    if isinstance(event, Prefilled):
        prompt = tokenizer.decode(event.context_info.tokens[:event.context_info._prompt_len])
        new_prompt = prompt.replace("foo", "bar")
        return actions.adjust_prefill(tokenizer.encode(new_prompt, add_special_tokens=False))
```

```python
# ✅ CORRECT - Initialization guard
@dataclass
class State:
    initialized: bool = False

states: dict[str, State] = {}

@mod
def good_prepend(event, actions, tokenizer):
    st = states.get(event.request_id)
    if not st:
        states[event.request_id] = State()
        st = states[event.request_id]
    
    if isinstance(event, Prefilled) and not st.initialized:
        st.initialized = True
        prompt = tokenizer.decode(event.context_info.tokens[:event.context_info._prompt_len])
        new_prompt = prompt.replace("foo", "bar")
        return actions.adjust_prefill(tokenizer.encode(new_prompt, add_special_tokens=False))
    return actions.noop()
```

---

## Building Your First Mod

### Example 1: Replace Phrase in Prompt

```python
from quote_mod_sdk import mod, Prefilled
from dataclasses import dataclass

@dataclass
class State:
    initialized: bool = False

states: dict[str, State] = {}

@mod
def replace_phrase(event, actions, tokenizer):
    st = states.get(event.request_id, State())
    states[event.request_id] = st
    
    if isinstance(event, Prefilled) and not st.initialized:
        st.initialized = True
        prompt = tokenizer.decode(
            event.context_info.tokens[:event.context_info._prompt_len]
        )
        new_prompt = prompt.replace("Say hi.", "Say bye.")
        new_tokens = tokenizer.encode(new_prompt, add_special_tokens=False)
        return actions.adjust_prefill(tokens=new_tokens)
    
    return actions.noop()
```

### Example 2: Inject Tokens at Start

```python
from quote_mod_sdk import mod, ForwardPass
from dataclasses import dataclass

@dataclass
class State:
    injected: bool = False

states: dict[str, State] = {}

@mod
def prepend_tokens(event, actions, tokenizer):
    st = states.get(event.request_id, State())
    states[event.request_id] = st
    
    if isinstance(event, ForwardPass) and not st.injected:
        st.injected = True
        injection = "Before I answer, let me think: "
        tokens = tokenizer.encode(injection, add_special_tokens=False)
        return actions.force_tokens(tokens=tokens)
    
    return actions.noop()
```

### Example 3: Mask Specific Token

```python
from quote_mod_sdk import mod, ForwardPass

@mod
def mask_token(event, actions, tokenizer):
    if isinstance(event, ForwardPass):
        logits = event.logits.to_numpy()
        # Mask em dash token
        em_dash_id = tokenizer.encode("—", add_special_tokens=False)[0]
        logits[em_dash_id] = -1e9
        from max.driver import Tensor
        return actions.adjust_logits(Tensor.from_numpy(logits))
    
    return actions.noop()
```

---

## Token Injection Patterns

### Pattern 1: Conditional Injection Based on Token Count

```python
from quote_mod_sdk import mod, ForwardPass, Added
from dataclasses import dataclass

@dataclass
class State:
    token_count: int = 0
    injected: bool = False

states: dict[str, State] = {}

@mod
def inject_at_position(event, actions, tokenizer):
    st = states.get(event.request_id, State())
    states[event.request_id] = st
    
    if isinstance(event, ForwardPass) and not st.injected:
        # Inject after 10 tokens
        if st.token_count >= 10:
            st.injected = True
            injection = " [IMPORTANT] "
            tokens = tokenizer.encode(injection, add_special_tokens=False)
            return actions.force_tokens(tokens=tokens)
    
    if isinstance(event, Added) and not st.injected:
        st.token_count += len(event.added_tokens)
    
    return actions.noop()
```

### Pattern 2: Detect and Replace Text

```python
from quote_mod_sdk import mod, Added
from dataclasses import dataclass

@dataclass
class State:
    accumulated_text: str = ""

states: dict[str, State] = {}

@mod
def detect_and_replace(event, actions, tokenizer):
    st = states.get(event.request_id, State())
    states[event.request_id] = st
    
    if isinstance(event, Added):
        # Only track non-forced tokens
        if not event.forced:
            text = tokenizer.decode(event.added_tokens)
            st.accumulated_text += text
            
            # Detect unwanted phrase
            needle = " I can't help with that"
            if st.accumulated_text.endswith(needle):
                # Backtrack and replace
                needle_tokens = tokenizer.encode(needle, add_special_tokens=False)
                replacement = " I can help you with that: "
                replacement_tokens = tokenizer.encode(replacement, add_special_tokens=False)
                return actions.backtrack(
                    steps=len(needle_tokens),
                    tokens=replacement_tokens
                )
    
    return actions.noop()
```

### Pattern 3: Inject After Sentence Boundary

```python
from quote_mod_sdk import mod, ForwardPass, Added
from dataclasses import dataclass

@dataclass
class State:
    period_count: int = 0
    injected: bool = False

states: dict[str, State] = {}

@mod
def inject_after_sentences(event, actions, tokenizer):
    st = states.get(event.request_id, State())
    states[event.request_id] = st
    
    if isinstance(event, ForwardPass) and not st.injected:
        # Inject after 2 sentences
        if st.period_count >= 2:
            st.injected = True
            injection = "\n\nAdditionally: "
            tokens = tokenizer.encode(injection, add_special_tokens=False)
            return actions.force_tokens(tokens=tokens)
    
    if isinstance(event, Added) and not st.injected:
        text = tokenizer.decode(event.added_tokens)
        st.period_count += text.count('.')
    
    return actions.noop()
```

---

## Uploading and Using Mods

### Installation

```bash
# Install CLI
cargo install concai

# Initialize project (creates .venv, installs SDK)
concai init
```

### Upload a Mod

```bash
# Single file
concai mod upload \
  --file-name my_mod.py \
  --url <endpoint-url> \
  --user-api-key <your-key>

# Directory (bundles all .py files)
concai mod upload \
  --dir mods/my_project \
  --url <endpoint-url> \
  --user-api-key <your-key>
```

### Use a Mod

Enable by appending `/<mod_name>` to model string:

```bash
curl -s <endpoint-url>/v1/chat/completions \
  -H 'content-type: application/json' \
  -H 'X-User-Api-Key: <your-key>' \
  -d '{
    "model": "modularai/Llama-3.1-8B-Instruct-GGUF/replace_phrase",
    "messages": [{"role":"user", "content":"Say hi."}]
  }'
```

The mod name matches your `@mod` function name (e.g., `replace_phrase`).

---

## Advanced Patterns

### Self-Prompting with Constraints

Use `SelfPrompt` for structured generation:

```python
from quote_mod_sdk import mod, Prefilled, ForwardPass, Added
from quote_mod_sdk.self_prompt import SelfPrompt, EraseMode
from quote_mod_sdk.strategies.strategy_constructor import ChoicesStrat

# Define self-prompt once
classifier = SelfPrompt(
    prompt={"text": " Choose: yes/no "},
    strategy=ChoicesStrat(["yes", "no"]),
    erase=EraseMode.ALL,  # Hide prompt + answer after
)

@mod
def classify_mod(event, actions, tokenizer):
    if isinstance(event, Prefilled):
        classifier.handle_prefilled(event, tokenizer)
        return actions.noop()
    
    if isinstance(event, ForwardPass):
        return classifier.handle_forward_pass(event, actions, tokenizer)
    
    if isinstance(event, Added):
        classifier.handle_added(event, actions, tokenizer)
        # Check if complete
        if classifier.is_complete(event.request_id):
            answer = tokenizer.decode(classifier.answer_tokens(event.request_id))
            print(f"Classification: {answer}")
        return actions.noop()
    
    return actions.noop()
```

### Flow Engine for Multi-Step Interactions

```python
from quote_mod_sdk import mod
from quote_mod_sdk.flow import FlowQuestion, FlowEngine, route_message
from quote_mod_sdk.strategies.strategy_constructor import ChoicesStrat

# Define questions
q_confirm = FlowQuestion(
    name="confirm",
    prompt=" Proceed? (yes/no): ",
    strategy=ChoicesStrat(["yes", "no"]),
)
q_confirm.on("yes", route_message("Confirmed!"))
q_confirm.on("no", route_message("Cancelled."))

ENGINE = FlowEngine(entry_question=q_confirm)

@mod
def flow_mod(event, actions, tokenizer):
    return ENGINE.handle_event(event, actions, tokenizer)
```

### Extracting Information from Prompts

```python
from quote_mod_sdk import mod, Prefilled
from dataclasses import dataclass

@dataclass
class State:
    initialized: bool = False
    extracted_info: str = ""

states: dict[str, State] = {}

@mod
def extract_info(event, actions, tokenizer):
    st = states.get(event.request_id, State())
    states[event.request_id] = st
    
    if isinstance(event, Prefilled) and not st.initialized:
        st.initialized = True
        prompt = tokenizer.decode(
            event.context_info.tokens[:event.context_info._prompt_len]
        )
        
        # Extract content between tags
        if "<information>" in prompt and "</information>" in prompt:
            start = prompt.find("<information>") + len("<information>")
            end = prompt.find("</information>")
            st.extracted_info = prompt[start:end]
            
            # Remove from prompt
            new_prompt = prompt[:prompt.find("<information>")] + prompt[end + len("</information>"):]
            new_tokens = tokenizer.encode(new_prompt, add_special_tokens=False)
            return actions.adjust_prefill(tokens=new_tokens)
    
    return actions.noop()
```

---

## Key Takeaways

1. **Always guard `Prefilled` initialization** — Use `initialized` flag to prevent re-running setup every step
2. **Track state per request** — Key state by `event.request_id`
3. **Track forced vs sampled tokens** — Use `event.forced` to ignore your own injections
4. **Use tokenizer for encoding/decoding** — Ensures consistency with serving model
5. **Return `actions.noop()` when not acting** — Required for all code paths
6. **Test incrementally** — Start simple, add complexity gradually

## Debugging Tips

```python
# Print to see mod execution
@mod
def debug_mod(event, actions, tokenizer):
    print(f"[DEBUG] Event: {type(event).__name__}, Request: {event.request_id[:8]}")
    
    if isinstance(event, Prefilled):
        print(f"[DEBUG] Prompt length: {event.context_info._prompt_len}")
    
    if isinstance(event, Added):
        text = tokenizer.decode(event.added_tokens)
        print(f"[DEBUG] Added: {repr(text)}, Forced: {event.forced}")
    
    return actions.noop()
```

---

## Resources

- [Full Documentation](https://docs.concordance.ai)
- [Examples Repository](https://github.com/concordance-co/concai-examples)
- [Contact Concordance](https://x.com/ConcordanceAI) for endpoint access
