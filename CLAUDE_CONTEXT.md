# Concordance (Quote) - Project Context

> Drop this file into Claude conversations to provide full context on this project.

## What Is This?

**Concordance** is an open-source inference stack for **observing, modifying, and controlling LLM generation in real-time**. Unlike traditional prompt engineering, Concordance lets you intervene at the token level during generation - forcing specific tokens, masking vocabulary, backtracking, or injecting content mid-stream.

The system has three main components:
1. **Engine** (Python) - Runs LLM inference with a "mod" system for token-level intervention
2. **Backend** (Rust) - Captures and stores detailed inference traces
3. **Frontend** (React) - Web UI for monitoring, debugging, and experimenting

## Why Does This Exist?

Traditional LLM interaction is limited to prompt engineering - you write a prompt and hope for the best. Concordance enables:

- **Token Injection**: Force specific words/phrases into the generation stream
- **Constrained Generation**: Ensure output follows a schema or picks from allowed options
- **Phrase Replacement**: Detect and replace specific phrases as they're generated
- **Backtracking**: Undo recent tokens and regenerate from an earlier point
- **Logit Manipulation**: Mask or bias token probabilities before sampling
- **Full Observability**: See exactly what happened at every generation step

## Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Frontend      │────▶│   Backend        │◀────│   Engine        │
│   (React)       │     │   (Rust/Axum)    │     │   (Python/MAX)  │
│   Port 3000     │     │   Port 6767      │     │   Port 8000     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                       │                        │
        │                       │                        │
   Web UI for            PostgreSQL DB            LLM inference
   monitoring &          for storing             with mod system
   playground            inference traces         & logging
```

## The Mod System (Core Innovation)

Mods are Python functions that intercept generation at critical points. They receive **events** and return **actions**.

### Events (What Mods Receive)

| Event | When It Fires | What You Can Do |
|-------|---------------|-----------------|
| `Prefilled` | After prompt processing, before generation starts | Setup, initialize state |
| `ForwardPass` | Before each token is sampled (has access to logits) | Mask tokens, bias probabilities |
| `Sampled` | After a token is selected but before it's committed | Inspect the choice, conditional logic |
| `Added` | After token(s) are added to the output | Track progress, detect patterns |

### Actions (What Mods Return)

```python
actions.noop()                      # Continue normally
actions.force_tokens(token_ids)     # Force specific tokens (skip sampling)
actions.adjust_logits(logits)       # Modify probability distribution
actions.backtrack(n, new_tokens)    # Remove n tokens, optionally replace
actions.force_output(tokens)        # End generation immediately
actions.tool_calls(payload)         # Emit structured tool call
```

### Example Mod

```python
from quote_mod_sdk import mod, ForwardPass, Added

@mod
def inject_after_greeting(event, actions, tokenizer):
    """Inject a phrase after the model says 'Hello'"""

    if isinstance(event, Added):
        text = tokenizer.decode(event.added_tokens)
        if "Hello" in text:
            injection = " (I'm secretly a robot)"
            tokens = tokenizer.encode(injection, add_special_tokens=False)
            return actions.force_tokens(tokens)

    return actions.noop()
```

## Directory Structure

```
/quote
├── /backend              # Rust backend (Axum + PostgreSQL)
│   ├── /src
│   │   ├── /handlers     # API endpoint handlers
│   │   │   ├── logs.rs           # Log retrieval & streaming
│   │   │   ├── ingest/           # Receives logs from engine
│   │   │   ├── playground.rs     # Token injection lab + SAE features
│   │   │   └── ...
│   │   ├── routes.rs     # Route definitions
│   │   └── main.rs
│   └── /migrations       # Database schema
│
├── /frontend             # React frontend (Vite + TypeScript)
│   ├── /src
│   │   ├── /components
│   │   │   ├── Playground.tsx           # Token injection experiments
│   │   │   ├── Playground/
│   │   │   │   ├── FeatureTimeline.tsx  # SAE feature visualization
│   │   │   │   └── ...
│   │   │   ├── LogsList.tsx             # Real-time log feed
│   │   │   ├── LogDetail/               # Detailed log inspection
│   │   │   └── TokenSequence/           # Token visualization
│   │   └── /lib
│   │       └── api.ts    # API client
│   └── ...
│
├── /engine               # Python inference engine
│   ├── /inference        # Core inference server
│   │   └── /src/quote
│   │       ├── /server/openai/local.py  # OpenAI-compatible server
│   │       ├── /hot/                    # Hot-reloadable execution
│   │       │   └── mod_inference.py     # Main inference loop with mods
│   │       ├── /mods/                   # Mod management
│   │       │   ├── manager.py           # ModManager registry
│   │       │   └── sdk_bridge.py        # Loads and executes mods
│   │       ├── /interpretability/       # SAE feature extraction
│   │       │   ├── sae_loader.py        # Loads LlamaScope SAEs
│   │       │   └── feature_extractor.py # Extracts features from activations
│   │       └── /logs/logger.py          # Sends traces to backend
│   │
│   ├── /sdk              # Mod authoring SDK (quote_mod_sdk)
│   │   └── /quote_mod_sdk
│   │       ├── mod.py           # @mod decorator
│   │       ├── actions.py       # Action builders
│   │       └── self_prompt.py   # Constrained generation helpers
│   │
│   ├── /shared           # Shared types (events, actions)
│   └── /examples         # Example mods
│
└── /cli                  # Rust CLI tool (concai)
```

## Key Features

### Token Injection Playground (`/frontend/src/components/Playground.tsx`)

A web UI for experimenting with token injection. Users can:
- Configure injection position (start, after N tokens, phrase replace, etc.)
- Set injection content
- Run experiments against Llama 3.1 8B or Qwen 14B
- View token-by-token results with forced tokens highlighted

### SAE Feature Analysis (`/engine/inference/src/quote/interpretability/`)

Post-hoc analysis of what happened inside the model:
- Uses **LlamaScope SAEs** (Sparse Autoencoders) to decompose hidden states into interpretable features
- Each feature can be looked up on **Neuronpedia** for human-readable descriptions
- Shows which features activate at injection points vs. natural generation

**How it works:**
1. After inference completes, take the final token sequence
2. Run a forward pass through the base model to get hidden states
3. SAE encodes hidden states → sparse feature activations
4. Display top features per position, link to Neuronpedia

### Inference Logging (`/backend/src/handlers/ingest/`)

The engine sends detailed traces to the backend:
- Every event (Prefilled, ForwardPass, Sampled, Added)
- Every action the mod took
- Token probabilities and timing
- Mod debug logs

### Real-time Monitoring (`/frontend/src/components/LogsList.tsx`)

- WebSocket streaming of new inference requests
- Filter by collection, API key, time range
- Click any log to see full token sequence and trace tree

## API Endpoints

### Engine (OpenAI-compatible)
- `POST /v1/chat/completions` - Run inference (append `/mod_name` to model to activate a mod)
- `POST /v1/mods` - Register a mod
- `GET /v1/models` - List available models
- `POST /extract_features` - Extract SAE features from token sequence
- `POST /analyze_features` - Get Claude to interpret feature patterns

### Backend
- `GET /logs` - List inference logs
- `GET /logs/stream` - SSE stream of new logs
- `GET /logs/:request_id` - Get detailed log
- `POST /v1/ingest` - Receive logs from engine
- `POST /playground/inference` - Run playground experiment
- `POST /playground/features/extract` - Extract features (proxies to engine)
- `POST /playground/features/analyze` - Analyze features with Claude

## Injection Positions

The playground supports various injection strategies:

| Position | Description | Use Case |
|----------|-------------|----------|
| `start` | Inject at generation start | Fake tool results, persona injection |
| `after_tokens` | Inject after N tokens | Mid-thought injection |
| `after_sentences` | Inject after N sentences | Between-thought injection |
| `eot_backtrack` | Inject before end-of-turn | Add final thoughts |
| `phrase_replace` | Detect phrase → replace | Censorship, concept replacement |
| `reasoning_start` | After `<think>` opens | Inject into reasoning (Qwen) |
| `reasoning_mid` | N tokens into reasoning | Steer reasoning (Qwen) |
| `reasoning_end` | Before `</think>` | Final reasoning injection (Qwen) |
| `response_start` | After `</think>` | Start of response (Qwen) |

## Database Schema (Key Tables)

- `requests` - Top-level inference request metadata
- `events` - Every event fired during generation (Prefilled, ForwardPass, etc.)
- `actions` - Every action a mod returned
- `mod_calls` - Record of mod invocations
- `mod_logs` - Debug output from mods
- `collections` - User-created groups of logs
- `api_keys` - Authentication

## Environment Variables

### Backend
```
DATABASE_URL=postgresql://...
PLAYGROUND_ADMIN_KEY=...           # Admin key for model servers
PLAYGROUND_LLAMA_8B_URL=...        # URL to Llama engine
PLAYGROUND_QWEN_14B_URL=...        # URL to Qwen engine
```

### Engine
```
HF_TOKEN=hf_...                    # HuggingFace token for model download
MODEL_ID=modularai/Llama-3.1-8B-Instruct-GGUF
QUOTE_LOG_INGEST_URL=http://localhost:6767  # Backend URL for logging
ANTHROPIC_API_KEY=sk-ant-...       # For Claude feature analysis
```

## Tech Stack

| Component | Technology | Why |
|-----------|------------|-----|
| Backend | Rust + Axum | Performance, type safety, async |
| Database | PostgreSQL | JSONB for flexible event storage |
| Frontend | React 19 + Vite | Fast dev, virtual scrolling for large logs |
| Engine | Python + MAX Engine | ML ecosystem, Modular's inference runtime |
| SAE | sae_lens + LlamaScope | Pre-trained interpretability tools |
| Deployment | Modal (optional) | Serverless GPUs for production |

## Common Workflows

### Running a Token Injection Experiment
1. Go to `/playground` in the frontend
2. Select model (Llama 8B or Qwen 14B)
3. Configure injection (position, content)
4. Click "Run Experiment"
5. View token sequence with forced tokens highlighted
6. Optionally extract SAE features to see what activated

### Writing a Custom Mod
1. Create a Python file with `@mod` decorated function
2. Handle events (ForwardPass, Added, etc.)
3. Return appropriate actions
4. Upload via `POST /v1/mods` or `concai mod upload`
5. Call with model string: `model_name/your_mod_name`

### Analyzing an Inference Log
1. Find log in frontend feed or search
2. Click to open detailed view
3. See token-by-token generation
4. Inspect trace tree for events/actions
5. Check mod logs for debug output

## Terminology

- **Mod**: Python function that intercepts generation
- **Event**: Notification at a critical point (ForwardPass, Added, etc.)
- **Action**: Response to an event (noop, force_tokens, etc.)
- **Forced token**: A token injected by a mod, not sampled
- **Backtrack**: Undo recent tokens and optionally replace
- **SAE**: Sparse Autoencoder - decomposes activations into interpretable features
- **Feature**: A learned direction in activation space with semantic meaning
- **Neuronpedia**: Database of SAE feature interpretations

## Current State

- **Working**: Full inference pipeline, mod system, logging, frontend visualization, token injection playground, SAE feature extraction
- **Experimental**: Claude-powered feature analysis
- **Models supported**: Llama 3.1 8B, Qwen 14B (reasoning model)
