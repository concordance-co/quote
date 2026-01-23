# Quote Mod SDK

The Quote Mod SDK lets you author Python mods that respond to runtime events (`PrefilledEvent`, `ForwardPassEvent`, etc.) and return Quote `ModAction` objects. Mods are registered via the server's `/v1/mods` endpoint and then enabled on chat requests by appending the mod name to the `model` string (for example, `modularai/Llama-3.1-8B-Instruct-GGUF/my_mod`).

## Installation

```bash
uv pip install -e sdk
```

## Authoring a mod

Use the `@mod` decorator to receive the event, an action builder constrained to that phase, and the active tokenizer. The builder always provides `noop()` and adds helpers such as `force_tokens`, `adjust_prefill`, or `force_output` depending on the phase.

```python
from sdk.quote_mod_sdk import ForwardPassEvent, mod, tokenize

@mod
def forward_injection(event, actions, tokenizer):
    if isinstance(event, ForwardPassEvent):
        tokens = tokenize("[ForwardInjected]", tokenizer)
        return actions.force_tokens(tokens)
    return actions.noop()
```

`tokenize(text, tokenizer)` uses the tokenizer supplied by the runtime so mods stay synchronized with whichever model is serving the request.

### Self-prompt with constrained generation

For common "self-prompt then constrain" flows, the SDK exposes
`self_prompt_constrained_mod`. It emits a `ForceTokens` action until the
injected prompt finishes streaming, then switches to `AdjustedLogits` so only a
given allow-list of token IDs remain viable.

```python
from sdk.quote_mod_sdk import self_prompt_constrained_mod

constrained = self_prompt_constrained_mod(
    prompt_text="<system>think step by step</system>",
    allowed_responses=[
        "hello world and bob",
        "hello bob",
        "hello world",
    ],
    mask_value=-1e9,
    tokenizer=model_tokenizer,
)
```

Attach `constrained` to a `ModManager` like any other mod. If `prompt_tokens`
are supplied, the helper tracks how many forced tokens remain by watching the
`AddedEvent.forced` flag; once all prefixed tokens are flushed, subsequent
`ForwardPass` events receive masked logits that admit only branches remaining in
the trie built from `allowed_responses`. When a branch reaches its terminal
string, the helper optionally appends a newline (configurable via
`completion_text`) so the model can emit a sentinel token and finish the
selection cleanly.

Provide the same tokenizer object used for generation (anything exposing
`encode(text, add_special_tokens=False)`), so the helper can resolve the prompt
and allowed responses eagerly without relying on ambient context.

Set `erase_after_complete="all"` to backtrack away both the injected prompt and
its constrained answer once classification is done, or
`erase_after_complete="prompt_only"` to remove just the prompt while reinserting
the answer tokens.

### Allowed actions per event

| Event | Helper methods |
|-------|----------------|
| `PrefilledEvent` | `noop`, `adjust_prefill`, `force_output`, `tool_calls` |
| `ForwardPassEvent` | `noop`, `force_tokens`, `backtrack`, `force_output`, `tool_calls`, `adjust_logits` |
| `SampledEvent` | `noop`, `force_tokens`, `backtrack`, `force_output`, `tool_calls` |
| `AddedEvent` | `noop`, `force_tokens`, `backtrack`, `force_output`, `tool_calls` |

Returning an action that is not valid for the current event raises `InvalidActionError` at runtime.

## Serializing and sending mods

Serialize a callable into a payload with `serialize_mod`. The payload captures the module source and the entrypoint name, which the server executes in a sandboxed namespace.

```python
from sdk.quote_mod_sdk import serialize_mod

payload = serialize_mod(forward_injection, name="forward_self_prompt")
```

POST this payload to `/v1/mods` to register it for later use:

```json
POST /v1/mods
{
  "name": "forward_self_prompt",
  "description": "Injects a fixed forward-pass token sequence",
  "language": "python",
  "module": "client_mod",
  "entrypoint": "forward_injection",
  "source": "...module source..."
}
```

Subsequent chat requests can enable the mod by appending the mod name to the model string:

```json
POST /v1/chat/completions
{
  "model": "modularai/Llama-3.1-8B-Instruct-GGUF/forward_self_prompt",
  "messages": [{"role": "user", "content": "Hello"}]
}
```

Only model strings with at least three slash-separated segments (`base/model/mod_name`) activate a registered mod; shorter names are treated as plain model requests.

On the server side, the loader validates the action per event before handing it to the Quote runtime. Mods are ephemeral and cleared when the server restarts.

## Agent example

`agent/mods.py` demonstrates how to define a mod with `@mod` and serialize it. `agent/main.py` shows how to attach the serialized payload to each chat request against the local OpenAI-compatible server.

## Troubleshooting

| Issue | Hint |
|-------|------|
| Invalid action error | Ensure you only call helper methods allowed for the current event |
| Missing entrypoint | Check that `serialize_mod` captured the correct function name and that it is defined at module scope |
| Decorator not found during execution | Include the import (`from quote_mod_sdk import mod`) in the module you serialize |
