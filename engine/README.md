# Quote Engine

A modular inference engine for Large Language Models with token-level intervention capabilities.

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-TBD-lightgrey.svg)](LICENSE)

## Overview

Quote is an inference engine that enables fine-grained control over LLM text generation through a powerful mod system. Unlike traditional approaches that only allow prompt engineering or post-processing, Quote lets you intervene at every step of the generation process—adjusting logits, forcing specific tokens, backtracking, or terminating early with custom output.

### Key Features

- **Token-Level Interventions**: React to generation events (prefill, forward pass, sampling, token addition) and modify behavior in real-time
- **Mod System**: Write Python mods that receive events and return actions to steer generation
- **Backtracking**: Rewind generation and replace tokens while maintaining KV cache consistency
- **Constrained Generation**: Force specific token sequences, adjust logit distributions, or constrain outputs to valid options
- **OpenAI-Compatible API**: Drop-in replacement for `/v1/chat/completions` with mod extensions
- **Hot Reloading**: Update execution logic without restarting the server

## Installation

### Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) package manager

### Quick Install

```bash
# Clone the repository
git clone https://github.com/concordance-co/quote.git
cd quote/engine

# Install dependencies
uv sync

# Install packages in development mode
uv pip install -e shared
uv pip install -e sdk
uv pip install -e inference
```

## Quick Start

### 1. Start the Server

```bash
cd inference
uv run -m quote.server.openai.local --host 0.0.0.0 --port 8000
```

### 2. Make a Request

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "modularai/Llama-3.1-8B-Instruct-GGUF",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 64
  }'
```

### 3. Write Your First Mod

```python
from quote_mod_sdk import mod, Prefilled, ForwardPass, Added

@mod
def my_first_mod(event, actions, tokenizer):
    """A simple mod that forces a greeting prefix."""
    
    if isinstance(event, ForwardPass):
        # Check if this is the first generated token
        if event.step == 0:
            greeting = "Greetings! "
            tokens = tokenizer.encode(greeting, add_special_tokens=False)
            return actions.force_tokens(tokens)
    
    return actions.noop()
```

### 4. Register and Use the Mod

```bash
# Register the mod
curl -X POST http://localhost:8000/v1/mods \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "my_first_mod",
    "language": "python",
    "module": "client_mod",
    "entrypoint": "my_first_mod",
    "source": "..."
  }'

# Use it by appending the mod name to the model
curl -X POST http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "modularai/Llama-3.1-8B-Instruct-GGUF/my_first_mod",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 64
  }'
```

## Project Structure

```
engine/
├── inference/          # Core inference engine
│   ├── src/quote/      # Main package
│   │   ├── hot/        # Hot-reloadable execution logic
│   │   ├── mods/       # Mod manager and SDK bridge
│   │   ├── pipelines/  # Text generation pipelines
│   │   └── server/     # HTTP server implementations
│   └── README.md       # Inference documentation
│
├── sdk/                # Mod authoring SDK
│   └── quote_mod_sdk/  # SDK package
│       ├── actions.py  # Action types (ForceTokens, Backtrack, etc.)
│       ├── mod.py      # @mod decorator
│       ├── flow.py     # Flow engine for multi-step interactions
│       └── strategies/ # Constrained generation strategies
│
├── shared/             # Shared types and utilities
│   └── src/shared/     # Common types, conversation management
│
├── examples/           # Example mods and demos
│   ├── demos/          # Simple demonstration mods
│   ├── json_schema/    # JSON Schema constrained generation
│   └── tau2/           # Complex agent workflow example
│
└── tests/              # Test suites
    ├── mod_unit_tests/ # Unit tests for mod actions
    └── inference/      # Integration tests
```

## Core Concepts

### Events

Mods receive events at critical points during generation:

| Event | When | Access |
|-------|------|--------|
| `Prefilled` | After prompt processing | Prompt tokens, context |
| `ForwardPass` | Before sampling | Raw logits |
| `Sampled` | After token selected | Sampled token ID |
| `Added` | After token(s) added | Added tokens, forced flag |

### Actions

Mods return actions to influence generation:

| Action | Effect |
|--------|--------|
| `noop()` | Continue normal generation |
| `force_tokens(tokens)` | Force specific tokens next |
| `adjust_logits(logits)` | Modify sampling distribution |
| `backtrack(n, tokens?)` | Remove last n tokens, optionally replace |
| `force_output(tokens)` | Immediately finalize with given tokens |
| `tool_calls(payload)` | Emit tool call response |
| `adjust_prefill(tokens)` | Replace input prompt tokens |

### Flow Engine

For complex multi-step interactions, use the Flow Engine:

```python
from quote_mod_sdk.flow import FlowQuestion, FlowEngine, route_message
from quote_mod_sdk.strategies import ChoicesStrat

confirm = FlowQuestion(
    name="confirm",
    prompt=" Proceed? ",
    strategy=ChoicesStrat(["yes", "no"]),
)
confirm.on("yes", route_message("Confirmed!"))
confirm.on("no", route_message("Cancelled."))

engine = FlowEngine(entry_question=confirm)
```

## Documentation

- [Inference Engine](inference/README.md) - Server setup, deployment, benchmarks
- [Mod SDK](sdk/README.md) - Writing and deploying mods
- [Shared Types](shared/README.md) - Event and action type reference
- [Building Mods Guide](examples/BUILDING_TOKEN_INJECTION_MODS.md) - Comprehensive mod authoring guide

## Examples

| Example | Description |
|---------|-------------|
| [demos/](examples/demos/) | Simple mods: backtracking, force output, logit adjustment |
| [json_schema/](examples/json_schema/) | Constrained generation following JSON Schema |
| [tau2/](examples/tau2/) | Complex airline customer service agent |

## Development

### Running Tests

```bash
# Run all tests
uv run pytest

# Run mod unit tests
cd tests/mod_unit_tests
uv run pytest
```

### Code Style

```bash
# Format code
uv run black .
uv run isort .

# Lint
uv run ruff check .
```

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under MIT. See [LICENSE](LICENSE) for details.

## Acknowledgments

Quote is built on top of [Modular's MAX Engine](https://www.modular.com/max) for high-performance inference.
