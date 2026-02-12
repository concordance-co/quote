# Engine Testing

This repo has multiple test styles. Use the right runner per suite.

## Fast local suites

Run these in the repo root:

```bash
engine/.venv/bin/python -m pytest -q engine/tests/test_activation_store.py engine/tests/test_generation.py
```

By marker:

```bash
engine/.venv/bin/python -m pytest -q -m unit engine/tests/test_activation_store.py
engine/.venv/bin/python -m pytest -q -m contract engine/tests/test_generation.py
```

## Mod unit harness (existing)

`engine/tests/mod_unit_tests` uses a custom harness and duplicate file basenames.
Use the harness runner (not broad pytest collection):

```bash
engine/.venv/bin/python engine/tests/mod_unit_tests/run_tests.py
```

## Integration and perf

- `integration`: real model/runtime wiring tests, slower and environment-sensitive.
- `fullpass`: true end-to-end generation loop tests using a real backend/model.
- `fullpass_sae`: optional full-pass + inline SAE extraction tests.
- `perf`: benchmark/regression checks (optional in local loops).

Run these explicitly when needed.

## Real full-pass runtime suite (manual foreground)

Default model is Llama 8B:

```bash
export QUOTE_FULLPASS_MODEL="meta-llama/Llama-3.1-8B-Instruct"
```

Run the full-pass runtime tests:

```bash
cd engine
uv run --package quote -m pytest -q -s tests/full_pass/test_hf_full_pass.py -m fullpass
```

Optional inline SAE test (heavier; requires `sae_lens` + SAE weights):

```bash
cd engine
export QUOTE_FULLPASS_ENABLE_SAE=1
export QUOTE_FULLPASS_SAE_ID="llama_scope_lxr_8x"
export QUOTE_FULLPASS_SAE_LAYER=16
# Optional: point at a local SAE directory (either direct SAE dir with cfg.json/sae_weights.safetensors
# or a parent directory containing per-layer subdirs like l16r_8x/)
export QUOTE_FULLPASS_SAE_LOCAL_PATH="/absolute/path/to/local/sae"
uv run --package quote -m pytest -q -s tests/full_pass/test_hf_full_pass.py -m fullpass_sae
```

## Visual full-pass debug UI

Run the local OpenAI-compatible server:

```bash
cd engine/inference
uv run -m quote.api.openai.local --host 0.0.0.0 --port 8000
```

Then open:

```text
http://127.0.0.1:8000/debug/fullpass
```

The UI lets you run local HF fullpass generation and inspect:
- output text + token IDs
- event/action summaries
- activation row preview
- feature delta timeline for a selected feature ID

See `engine/inference/FULLPASS_DEBUG.md` for full model/SAE precedence, storage paths, and troubleshooting.
