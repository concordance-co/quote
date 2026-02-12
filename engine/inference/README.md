# Containerized Inference

## Makefile Quick Commands

Set defaults once, then use Make targets for local and remote.

```
cp .servers.example .servers
$EDITOR .servers    # set DEV_BASE and OPENAI_BASE
```

- Local
  - `make dev-local` (POST /complete on 8001)
  - `make gen-local-dev P="Say hi" T=64`
  - `make openai-local` (OpenAI API on 8000)
  - `make gen-local-openai P="Say hi" T=64`
  - `make gen-local-openai-stream P="Stream me" T=64`

- Remote (Modal)
  - `make dev-remote` (start dev app)  •  `make publish-remote-dev`  •  `make gen-remote-dev P="Hello" T=32`
  - `make openai-remote` (start OpenAI app)  •  `make publish-remote-openai`  •  `make gen-remote-openai P="Hello" T=32`  •  `make gen-remote-openai-stream P="Stream" T=32`

Hot-swap while local: edit and save `src/quote/hot/execute_impl.py`; the servers auto‑reload on each request.

Two inference loops are available and can be toggled without code changes:

- `src/quote/hot/vanilla_inference.py` — delegates to the pipeline's built-in `execute()`.
- `src/quote/hot/mod_inference.py` — custom loop (current default behavior).

Switch locally (copies into `hot/execute_impl.py`):

```
make use-vanilla   # use vanilla_inference.py
make use-mod       # use mod_inference.py
make save-mod      # if you edited execute_impl.py directly, persist changes into mod_inference.py
make diff-mod      # show diffs between mod_inference.py and execute_impl.py
make use-backup    # restore the latest backup, or pass FILE=... to pick one
```

Note: switching (`use-vanilla` / `use-mod`) creates a timestamped backup of the current
`execute_impl.py` in `src/quote/hot/backups/` if it differs from the target.

To restore your last WIP after trying vanilla, use:

```
make use-backup                # restores the newest backup
make use-backup FILE=src/quote/hot/backups/execute_impl.backup.20250101-121314.py
```

Publish a specific loop to remote (keeps remote `/logic/execute_impl.py` self-contained):

```
make publish-remote-openai-vanilla   # or ...-mod
make publish-remote-dev-vanilla      # or ...-mod
```

## Quick Start (Local) - UV

Local servers run without Modal for fast iteration. Here are uv commands instead of `make`

### 2-Minute Fullpass Debug Quickstart

From `engine/inference`:

```bash
export TOKENIZERS_PARALLELISM=false
uv run -m quote.server.openai.local --host 0.0.0.0 --port 8000
```

Then open:

```text
http://127.0.0.1:8000/debug/fullpass
```

Use defaults in the UI (`meta-llama/Llama-3.1-8B-Instruct`, `llama_scope_lxr_8x`, layer `16`) and click **Run Fullpass**.

- Start Dev server (complete/exec_info):

```
uv run -m quote.server.dev.local --host 0.0.0.0 --port 8001
```

- Start OpenAI-compatible server (/v1/*):

```
uv run -m quote.server.openai.local --host 0.0.0.0 --port 8000
```

- Fullpass debug UI (runtime + activations):

```
# after starting local OpenAI server
open http://127.0.0.1:8000/debug/fullpass
```

See `FULLPASS_DEBUG.md` for model/SAE selection rules, activation DB paths, and troubleshooting.

- Use the router CLI (ergonomic wrapper around curl):

```
uv run src/quote/server/router.py --mode local-dev --action generate --prompt "Say hi" --max_tokens 32
uv run src/quote/server/router.py --mode local-openai --action generate --prompt "Say hi" --max_tokens 32
uv run src/quote/server/router.py --mode local-openai --action generate --prompt "Stream me" --max_tokens 32 --stream
uv run src/quote/server/router.py --mode local-openai --action health
```

## Dev Server (Remote via Modal)

Setup (once):

- Install the package in editable mode so `quote` is importable locally:

`uv pip install -e .`

1. Serve the containerized inference loop:

`modal serve src/quote/server/dev/remote.py`

2. That will spit out a base URL to your ASGI app (defaults live in `.servers`).

3. Hot-swap the execute() logic used by the running container (router):

```
uv run src/quote/server/router.py --mode remote-dev --action publish-exec --file ./src/quote/hot/execute_impl.py
```

4. Run inference against the updated logic (router):

```
uv run src/quote/server/router.py --mode remote-dev --action generate --prompt "hello" --max_tokens 64
```

## OpenAI-Compatible Server (Remote via Modal)

Expose OpenAI-style endpoints (`/v1/models`, `/v1/chat/completions`) with the same hot-swap `execute()` behavior used in development.

- Serve the OpenAI ASGI app:

`modal serve src/quote/server/openai/remote.py`

- Hot-swap the `execute()` logic via HTTP (replace BASE with your served URL):

`curl -sS -X POST "$YOUR_MODAL_ENDPOINT/publish_exec" -H 'Content-Type: application/octet-stream' --data-binary @src/quote/hot/execute_impl.py`

- Inspect current hot-swap status:

`curl -sS "$YOUR_MODAL_ENDPOINT/exec_info" | jq`

- Non-streaming chat completion (for remote servers with per-user mods, include header `X-User-Api-Key: <your_key>` when using mods):

```
curl -sS -X POST "$YOUR_MODAL_ENDPOINT/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -H 'X-User-Api-Key: <your_key>' \
  -d '{
    "model": "modularai/Llama-3.1-8B-Instruct-GGUF",
    "messages": [
      {"role":"system","content":"You are concise."},
      {"role":"user","content":"Say hi in <=5 words."}
    ],
    "max_tokens": 64,
    "temperature": 0.7,
    "top_p": 0.9
  }'
```

- Streaming SSE chat completion:

```
curl -N -sS -X POST "$YOUR_MODAL_ENDPOINT/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -H 'X-User-Api-Key: <your_key>' \
  -d '{
    "model": "modularai/Llama-3.1-8B-Instruct-GGUF",
    "messages": [
      {"role":"system","content":"You are concise."},
      {"role":"user","content":"Stream a verbose greeting."}
    ],
    "max_tokens": 64,
    "temperature": 0.7,
    "top_p": 0.9,
    "stream": true
  }'
```

Notes
- The OpenAI server uses the same in-memory pipeline and hot-swap module as the dev server.
- Usage token counts are currently stubbed (0s) in non-streaming responses.
- Use the HTTP `/publish_exec` endpoint for hot-swapping. Avoid `modal run` for this server, as it creates a separate ephemeral app and different endpoint.

### OpenAI Param Examples

- Response format: JSON object

```
curl -sS -X POST "$YOUR_MODAL_ENDPOINT/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "modularai/Llama-3.1-8B-Instruct-GGUF",
    "messages": [
      {"role":"user","content":"Return a JSON object with foo and bar fields."}
    ],
    "response_format": {"type": "json_object"},
    "max_tokens": 128
  }' | jq
```

- Response format: JSON schema

```
curl -sS -X POST "$YOUR_MODAL_ENDPOINT/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "modularai/Llama-3.1-8B-Instruct-GGUF",
    "messages": [
      {"role":"user","content":"Provide schema info for Seattle."}
    ],
    "response_format": {
      "type": "json_schema",
      "json_schema": {
        "schema": {
          "type": "object",
          "properties": {"city": {"type":"string"}, "temp_c": {"type":"number"}},
          "required": ["city","temp_c"],
          "additionalProperties": false
        }
      }
    },
    "max_tokens": 128
  }' | jq
```

- Tools: function, auto tool_choice (non-streaming). If the model emits tool calls JSON, response contains tool_calls.

```
curl -sS -X POST "$YOUR_MODAL_ENDPOINT/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "modularai/Llama-3.1-8B-Instruct-GGUF",
    "messages": [
      {"role":"user","content":"Whats the weather in Boston?"}
    ],
    "tools": [
      {"type":"function","function":{
        "name":"get_weather",
        "description":"Get current weather by city",
        "parameters": {"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}
      }}
    ],
    "tool_choice": "auto",
    "max_tokens": 128
  }' | jq
```

- Tools: explicit none (forces regular text output)

```
curl -sS -X POST "$YOUR_MODAL_ENDPOINT/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "modularai/Llama-3.1-8B-Instruct-GGUF",
    "messages": [
      {"role":"user","content":"Brief instructions to the assistant."}
    ],
    "tools": [{"type":"function","function":{"name":"noop"}}],
    "tool_choice": "none",
    "max_tokens": 64
  }' | jq
```

- Streaming + tools (expected 400 error; tools not supported in streaming mode)

```
curl -i -N -sS -X POST "$YOUR_MODAL_ENDPOINT/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "modularai/Llama-3.1-8B-Instruct-GGUF",
    "messages": [{"role":"user","content":"Try calling a tool while streaming"}],
    "tools": [{"type":"function","function":{"name":"get_time"}}],
    "tool_choice": "auto",
    "stream": true
  }'
```
Router equivalents (use defaults from `.servers`):

```
# Dev app
uv run src/quote/server/router.py --mode remote-dev --action publish-exec --file src/quote/hot/execute_impl.py
uv run src/quote/server/router.py --mode remote-dev --action health
uv run src/quote/server/router.py --mode remote-dev --action generate --prompt "hello" --max_tokens 64

# OpenAI app
uv run src/quote/server/router.py --mode remote-openai --action health
uv run src/quote/server/router.py --mode remote-openai --action publish-exec --file src/quote/hot/execute_impl.py
uv run src/quote/server/router.py --mode remote-openai --action generate --prompt "Say hi" --max_tokens 64
uv run src/quote/server/router.py --mode remote-openai --action generate --prompt "Stream me" --max_tokens 64 --stream
```

## Makefile Shortcuts

Common commands are wrapped in a Makefile:

```
make dev-local                 # start local dev server (8001)
make openai-local              # start local openai server (8000)
make dev-remote                # modal serve dev
make openai-remote            # modal serve openai

make health-local-dev
make gen-local-dev P="Say hi" T=64
make gen-local-openai P="Say hi" T=64
make gen-local-openai-stream P="Stream me" T=64

# Set URLs from modal output
make health-remote-dev BASE=...
make gen-remote-dev BASE=... P="Say hi" T=64
make publish-remote-dev BASE=...

# Set BASE from modal output
make health-remote-openai BASE=...
make gen-remote-openai BASE=... P="Say hi" T=64
make gen-remote-openai-stream BASE=... P="Stream me" T=64
make publish-remote-openai BASE=...
make publish-remote-openai-vanilla BASE=...
make publish-remote-openai-mod BASE=...
make publish-remote-dev-vanilla BASE=...
make publish-remote-dev-mod BASE=...
```
---
## Running Benchmarks:

### BFCL
Clone the repo at https://github.com/ShishirPatil/gorilla/tree/main

Navigate to the BFCL directory (bfc_eval) and `cp .env.example .env`

Make sure to set the base URL for the right environment:
```
# Provide the API key for the model(s) you intend to use
# For local OpenAI-compatible servers, any non-empty value typically works
# If using the Functionary-compatible path below, keep this as "functionary"
OPENAI_API_KEY=EMPTY
# Point OpenAI SDK calls to your local OpenAI-compatible server
OPENAI_BASE_URL=http://localhost:8000/v1      # $YOUR_MODAL_ENDPOINT/v1 for Modal
```

Add supported models to the list in berkeley-function-call-leaderboard/bfcl_eval/constants/supported_models.py, if testing on models not in the list:

```
    "modularai/Llama-3.1-8B-Instruct-GGUF-FC",
    "modularai/Llama-3.1-8B-Instruct-GGUF",
```

Additionally, add the following ModelConfigs to model_config.py in the same directory:

```
# Custom OpenAI-compatible server model (local)
    "modularai/Llama-3.1-8B-Instruct-GGUF-FC": ModelConfig(
        model_name="modularai/Llama-3.1-8B-Instruct-GGUF-FC",
        display_name="Llama-3.1-8B-Instruct-GGUF (FC)",
        url="http://localhost:8000/v1",
        org="ModularAI",
        license="",
        model_handler=OpenAICompletionsHandler,
        input_price=None,
        output_price=None,
        is_fc_model=True,
        underscore_to_dot=True,
    ),
    "modularai/Llama-3.1-8B-Instruct-GGUF": ModelConfig(
        model_name="modularai/Llama-3.1-8B-Instruct-GGUF",
        display_name="Llama-3.1-8B-Instruct-GGUF (Prompt)",
        url="http://localhost:8000/v1",
        org="ModularAI",
        license="",
        model_handler=OpenAICompletionsHandler,
        input_price=None,
        output_price=None,
        is_fc_model=False,
        underscore_to_dot=False,
    ),
```

From there, it should be straightforward to use the CLI to generate and score:

`BFCL_PROJECT_ROOT=$(pwd) OPENAI_API_KEY=functionary OPENAI_BASE_URL=http://localhost:8000/v1 python -m bfcl_eval generate --model modularai/Llama-3.1-8B-Instruct-GGUF-FC --test-category simple_python --temperature 0.001`


## tau2

1. clone the repo
2. create a venv
3. activate the venv
4. `uv pip install -e .`
then try:
```
tau2 run --domain airline --num-tasks 1 --num-trials 1 --log-level CRITICAL --agent-llm modularai/Llama-3.1-8B-Instruct-GGUF --agent-llm-args '{"base_url":"$YOUR_MODAL_ENDPOINT/v1","custom_llm_provider":"openai","api_key":"dummy","timeout":120,"max_tokens":1024}' --user-llm modularai/Llama-3.1-8B-Instruct-GGUF --user-llm-args '{"base_url":"$YOUR_MODAL_ENDPOINT/v1","custom_llm_provider":"openai","api_key":"dummy","timeout":120,"max_tokens":1024}'
```
try:
`tau2 view`
to view results and shit


## Devving Mods
1. Author a mod in Python (see `sdk/quote_mod_sdk/mod.py` and the examples in `agent/mods.py`).
2. Serialize it with `quote_mod_sdk.serialize_mod(...)`, providing a unique `name`.
3. `POST` the serialized payload to `/v1/mods` on the OpenAI-compatible server.
4. When calling `/v1/chat/completions`, append `/<mod_name>` to the `model` string to enable the registered mod, e.g., `modularai/Llama-3.1-8B-Instruct-GGUF/my_mod`.

Mods are stored in-memory for the lifetime of the server process; restart the server to clear them.

Note: mods are only activated when the `model` value contains at least three slash-separated segments (`base/model/mod_name`).
