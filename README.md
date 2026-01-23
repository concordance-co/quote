# Concordance

Concordance is an open-source inference stack that lets you **observe, modify, and control LLM generation in real-time**. It provides:

- **Quote Engine** — An inference server with a programmable mod system for token-level intervention
- **Thunder Backend** — Observability service that captures full inference traces
- **Web UI** — Frontend for exploring traces, viewing mod actions, and debugging generation
- **CLI** — Command-line tool for local development and mod management

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Frontend  │────▶│   Backend   │◀────│   Engine    │
│  (React/TS) │     │ (Rust/Axum) │     │  (Python)   │
└─────────────┘     └─────────────┘     └─────────────┘
     :3000              :6767               :8000
```


## Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager
- [Rust toolchain](https://rustup.rs/) — For backend and CLI
- [Node.js 20+](https://nodejs.org/) — For frontend
- [Hugging Face account](https://huggingface.co/) — For model access (get a token at [hf.co/settings/tokens](https://huggingface.co/settings/tokens))
- PostgreSQL database — We recommend [Neon](https://neon.tech) (see below)

## Getting Started

### Step 1: Set Up the Database

The backend requires a PostgreSQL database. We recommend **Neon** for a free, serverless Postgres:

1. Create an account at [neon.tech](https://neon.tech)
2. Create a new project
3. Copy your connection string from the dashboard (looks like `postgresql://user:pass@ep-xxx.region.aws.neon.tech/dbname`)

See [Neon's quickstart guide](https://neon.tech/docs/get-started-with-neon/signing-up) for detailed instructions.

### Step 2: Start the Backend

```bash
cd backend
cp .env.example .env
```

Edit `.env` and set your database URL:
```
DATABASE_URL=postgresql://user:pass@ep-xxx.region.aws.neon.tech/dbname?sslmode=require
```

Then run:
```bash
cargo run
```

The backend will automatically run database migrations on first start. Verify it's running:
```bash
curl http://localhost:6767/healthz
```

### Step 3: Start the Engine

The engine runs the LLM inference with mod support.

```bash
cd engine/inference
```

Create a `.env` file with your Hugging Face token:
```
HF_TOKEN=hf_your_token_here
MODEL_ID=modularai/Llama-3.1-8B-Instruct-GGUF
```

Start the server:
```bash
uv run -m quote.server.openai.local --host 0.0.0.0 --port 8000
```

> **Note:** First run downloads the model and compiles it, which takes several minutes. Subsequent starts are faster.

Test the engine:
```bash
curl http://localhost:8000/v1/models
```

### Step 4: Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

## Writing Mods

Mods let you intercept and modify inference at the token level. Here's a simple example:

```python
from quote_mod_sdk import mod, ForwardPassEvent, tokenize

@mod
def inject_thinking(event, actions, tokenizer):
    if isinstance(event, ForwardPassEvent) and event.step == 0:
        tokens = tokenize("<think>", tokenizer)
        return actions.force_tokens(tokens)
    return actions.noop()
```

Upload mods to a running server:
```bash
# Install the CLI first
cargo install --path cli

# Upload your mod
concai mod upload --file-name my_mod.py
```

Then enable the mod in your API calls by appending the mod name to the model:
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "modularai/Llama-3.1-8B-Instruct-GGUF/inject_thinking",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

See [engine/sdk/README.md](engine/sdk/README.md) for the full mod authoring guide.

## Deployment (Modal)

For GPU inference in production, deploy the engine to [Modal](https://modal.com):

```bash
cd engine/inference
modal serve src/quote/server/openai/remote.py
```

Modal provides serverless GPU instances that scale to zero when not in use. See [engine/inference/README.md](engine/inference/README.md) for full deployment details.

## Component Documentation

| Component | Description | Docs |
|-----------|-------------|------|
| **Engine** | Inference server with mod system | [engine/inference/README.md](engine/inference/README.md) |
| **Mod SDK** | Python SDK for authoring mods | [engine/sdk/README.md](engine/sdk/README.md) |
| **Backend** | Observability and logging service | [backend/README.md](backend/README.md) |
| **CLI** | Command-line tool | [cli/README.md](cli/README.md) |
| **Frontend** | Web UI | [frontend/README.md](frontend/README.md) |

## Configuration Reference

| Variable | Component | Description |
|----------|-----------|-------------|
| `DATABASE_URL` | Backend | Postgres connection string |
| `HF_TOKEN` | Engine | Hugging Face token for model downloads |
| `MODEL_ID` | Engine | Model to load (default: `modularai/Llama-3.1-8B-Instruct-GGUF`) |
| `VITE_WS_URL` | Frontend | WebSocket URL for log streaming (default: `ws://localhost:6767`) |

See each component's `.env.example` for all available options.

## Project Structure

```
concordance/
├── backend/          # Rust observability service (Thunder)
├── cli/              # Rust CLI tool (concai)
├── engine/
│   ├── inference/    # Python inference server (Quote)
│   ├── sdk/          # Mod SDK
│   └── shared/       # Shared utilities
├── frontend/         # React web UI
└── scripts/          # Build and release scripts
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests (`cargo test`, `uv run pytest`, `npm test`)
5. Submit a pull request

## License

MIT
