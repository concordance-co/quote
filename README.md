# Concordance

Concordance is an open-source inference stack that lets you **observe, modify, and control LLM generation in real-time**. It provides:

- **Quote Engine** — An inference server with a programmable mod system for token-level intervention
- **Thunder Backend** — Observability service that captures full inference traces
- **Web UI** — Frontend for exploring traces, viewing mod actions, and debugging generation
- **CLI** — Command-line tool for local development and mod management

## Table of Contents

- [Architecture](#architecture)
- [Quick Start](#quick-start)
  - [Prerequisites](#prerequisites)
  - [Before Running Setup](#before-running-setup)
  - [Run the Setup Script](#run-the-setup-script)
  - [Start the Services](#start-the-services)
- [Manual Setup](#manual-setup)
  - [Step 1: Set Up the Database](#step-1-set-up-the-database)
  - [Step 2: Start the Backend](#step-2-start-the-backend)
  - [Step 3: Start the Engine](#step-3-start-the-engine)
  - [Step 4: Start the Frontend](#step-4-start-the-frontend)
- [Writing Mods](#writing-mods)
- [Deployment (Modal)](#deployment-modal)
- [Component Documentation](#component-documentation)
- [Configuration Reference](#configuration-reference)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Frontend  │────▶│   Backend   │◀────│   Engine    │
│  (React/TS) │     │ (Rust/Axum) │     │  (Python)   │
└─────────────┘     └─────────────┘     └─────────────┘
     :3000              :6767               :8000
```

## Quick Start

The fastest way to get Concordance running is with our interactive setup script.

### Prerequisites

Before running the setup script, make sure you have the following installed:

| Tool | Purpose | Installation |
|------|---------|--------------|
| [uv](https://docs.astral.sh/uv/) | Python package manager | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [Rust](https://rustup.rs/) | Backend and CLI | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |
| [Node.js 18+](https://nodejs.org/) | Frontend | Download from nodejs.org or use your package manager |
| [psql](https://www.postgresql.org/) | Database migrations | `brew install postgresql` (macOS) or `apt install postgresql-client` (Linux) |

You'll also need:
- A [Hugging Face account](https://huggingface.co/) with an API token ([get one here](https://huggingface.co/settings/tokens))

### Before Running Setup

**1. Set up a PostgreSQL database**

The backend requires a PostgreSQL database. We recommend [Neon](https://neon.tech) for a free, serverless Postgres:

1. Create an account at [neon.tech](https://neon.tech)
2. Create a new project
3. Copy your connection string from the dashboard

Your connection string will look like:
```
postgresql://user:pass@ep-xxx.region.aws.neon.tech/dbname?sslmode=require
```

**2. Get your Hugging Face token**

1. Go to [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
2. Create a new token with read access
3. Copy the token (starts with `hf_`)

### Run the Setup Script

Clone the repository and run the interactive setup:

```bash
git clone https://github.com/concordance-co/quote.git
cd quote
./setup.sh
```

The setup script will guide you through configuring all components:

| Step | What it configures |
|------|-------------------|
| **Prerequisites Check** | Verifies uv, Rust, Node.js, npm are installed; optionally installs missing tools |
| **Backend Setup** | Database URL, server host/port, bootstrap secret, playground settings |
| **Database Migrations** | Runs SQL migrations to create required tables |
| **Engine Setup** | HF token, admin key, model ID, deployment mode (local/Modal), server settings |
| **Frontend Setup** | API URL, WebSocket URL for real-time streaming |
| **Dependency Installation** | Builds backend, installs Python/Node packages |

You can also run setup for individual components:
```bash
./setup.sh --quick backend   # Set up only the backend
./setup.sh --quick engine    # Set up only the engine
./setup.sh --quick frontend  # Set up only the frontend
./setup.sh --quick all       # Set up everything (non-interactive defaults)
```

### Start the Services

After setup, use the run script to start all services:

```bash
./run.sh start          # Start all services
./run.sh status         # Check service status
./run.sh logs engine    # View engine logs
./run.sh stop           # Stop all services
```

Or start services individually:
```bash
./run.sh start backend
./run.sh start engine
./run.sh start frontend
```

Once running:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:6767
- **Engine API**: http://localhost:8000

**Ready to build your first mod?** Visit [docs.concordance.co](https://docs.concordance.co) to get started!

---

## Manual Setup

If you prefer to set things up manually, follow these steps:

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

Run database migrations:
```bash
./run_migration.sh
```

Then start the server:
```bash
cargo run
```

Verify it's running:
```bash
curl http://localhost:6767/healthz
```

### Step 3: Start the Engine

The engine runs the LLM inference with mod support.

```bash
cd engine
```

Create an `inference/.env` file with your Hugging Face token:
```
HF_TOKEN=hf_your_token_here
MODEL_ID=modularai/Llama-3.1-8B-Instruct-GGUF
```

Install dependencies and start the server:
```bash
uv sync --all-packages
uv pip install -e inference
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

Open [http://localhost:3000](http://localhost:3000) in your browser.

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

See [engine/sdk/README.md](engine/sdk/README.md) for the full mod authoring guide, or visit [docs.concordance.co](https://docs.concordance.co) to build your first mod!

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

### Backend

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | Postgres connection string |
| `APP_HOST` | No | Server bind address (default: `127.0.0.1`) |
| `APP_PORT` | No | Server port (default: `6767`) |
| `BOOTSTRAP_SECRET` | No | Secret for creating initial admin API key |
| `PLAYGROUND_ADMIN_KEY` | No | Admin key for playground feature |
| `PLAYGROUND_LLAMA_8B_URL` | No | Modal URL for Llama 8B playground |
| `PLAYGROUND_QWEN_14B_URL` | No | Modal URL for Qwen 14B playground |

### Engine

| Variable | Required | Description |
|----------|----------|-------------|
| `HF_TOKEN` | Yes* | Hugging Face token for model downloads |
| `MODEL_ID` | No | Model to load (default: `modularai/Llama-3.1-8B-Instruct-GGUF`) |
| `ADMIN_KEY` | No | Admin key for authenticated operations |
| `HOST` | No | Server bind address (default: `0.0.0.0`) |
| `PORT` | No | Server port (default: `8000`) |
| `USERS_PATH` | No | Path to users JSON (default: `./users/users.json`) |
| `MODS_BASE` | No | Base path for mods storage (default: `./mods`) |
| `QUOTE_LOG_INGEST_URL` | No | Backend URL for sending inference logs |

### Frontend

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_API_URL` | No | Backend API URL (default: `/api`) |
| `VITE_WS_URL` | No | WebSocket URL for log streaming (default: `ws://localhost:6767`) |

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
├── scripts/          # Build and release scripts
├── setup.sh          # Interactive setup script
└── run.sh            # Service management script
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