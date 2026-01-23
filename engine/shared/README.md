# Shared

Common types, utilities, and conversation management for the Quote inference engine.

## Overview

The `shared` package provides foundational types and utilities used by both the Quote inference engine (`quote`) and the mod SDK (`quote_mod_sdk`). This package ensures consistent type definitions and shared functionality across all components.

## Installation

```bash
uv pip install -e shared
```

## Components

### Types (`shared.types`)

Core event and action types for the mod system:

**Events** - Emitted during inference to inform mods of generation state:
- `Prefilled` - After prompt processing, before generation begins
- `ForwardPass` - Before token sampling, with access to logits
- `Sampled` - After a token is sampled (before it's added to output)
- `Added` - After token(s) are added to the generation buffer

**Actions** - Returned by mods to influence generation:
- `Noop` - No action; continue normal generation
- `ForceTokens` - Force specific tokens to be emitted next
- `ForceOutput` - Immediately finalize output with given tokens
- `AdjustedLogits` - Modify logit distribution before sampling
- `AdjustedPrefill` - Replace input prompt tokens
- `Backtrack` - Remove recent tokens and optionally replace them
- `ToolCalls` - Emit a tool call instead of text
- `EmitError` - Signal an error condition

### Conversation (`shared.conversation`)

Thread-safe conversation context management for multi-request servers:

```python
from shared.conversation import (
    set_conversation,
    get_conversation,
    clear_conversation,
    set_schemas,
    get_schemas,
)

# Store conversation for a request
set_conversation(request_id, messages)

# Retrieve conversation in a mod
messages = get_conversation()

# Clean up after request completes
clear_conversation(request_id)
```

### Utilities (`shared.utils`)

Common utility functions used across the codebase.

## Usage

This package is primarily used internally by `quote` and `quote_mod_sdk`. Direct usage is typically not needed unless you're extending the core system.

```python
from shared.types import ForwardPass, ForceTokens, AdjustedLogits
from shared.conversation import get_conversation, set_schemas
```

## License

See [LICENSE](./LICENSE) for details.