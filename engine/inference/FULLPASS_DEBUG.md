# Fullpass Debug UI

This is a local inspection UI for the engine runtime path. It is meant for fast manual validation of:
- real HF generation loop behavior
- mod event/action flow
- inline SAE feature extraction
- activation persistence/querying

## Start

From repo root:

```bash
cd engine/inference
export TOKENIZERS_PARALLELISM=false
uv run -m quote.server.openai.local --host 0.0.0.0 --port 8000
```

Open:

```text
http://127.0.0.1:8000/debug/fullpass
```

## What Model Is Used

Two model stacks exist when the server is running:

- OpenAI endpoint stack (`/v1/chat/completions`):
  - defaults to `MODEL_ID` or `modularai/Llama-3.1-8B-Instruct-GGUF`
- Fullpass debug UI stack (`/debug/fullpass/*`):
  - uses HF backend
  - model precedence:
    1. `model_id` from UI request body
    2. `QUOTE_FULLPASS_MODEL`
    3. `CONCORDANCE_MODEL`
    4. `meta-llama/Llama-3.1-8B-Instruct`

## SAE Settings

For `/debug/fullpass/run` with `inline_sae=true`, SAE config precedence is:

- `sae_id`: request `sae_id` -> `QUOTE_FULLPASS_SAE_ID` -> config default
- `sae_layer`: request `sae_layer` -> `QUOTE_FULLPASS_SAE_LAYER` -> config default
- `sae_top_k`: request `sae_top_k` -> `QUOTE_FULLPASS_SAE_TOP_K` -> config default
- `sae_local_path`: request `sae_local_path` -> `QUOTE_FULLPASS_SAE_LOCAL_PATH` -> `CONCORDANCE_SAE_LOCAL_PATH`

Local SAE path can point to:
- direct SAE dir containing `cfg.json` and `sae_weights.safetensors`
- parent dir containing layer subdir (for example `l16r_8x/`)

## Activation Storage

Activation rows are written to local DuckDB/Parquet through `ActivationStore`.

Default paths (from `engine/` cwd):
- DuckDB: `artifacts/activations/activations.duckdb`
- Parquet root: `artifacts/activations/parquet/`

`/debug/fullpass` shows:
- activation preview rows for the current request
- feature delta timeline for selected feature id

## Debug Endpoints

- `GET /debug/fullpass` UI
- `POST /debug/fullpass/run` run fullpass
- `GET /debug/fullpass/feature-deltas` query feature deltas

## Logging You Should See

Server logs include:
- fullpass runtime init (activation store config)
- backend load/reuse/shutdown with resolved HF model
- run summary: request_id, duration, output token count, activation row count
- feature delta query summary

## Quick Troubleshooting

- `mps/cpu` SAE device mismatch:
  - fixed in extractor; restart server after pulling latest changes
- no activation rows:
  - ensure `collect_activations=true` and `inline_sae=true`
  - confirm SAE load succeeded for chosen `sae_id/layer`
- tokenizer parallelism warning:
  - set `TOKENIZERS_PARALLELISM=false`
