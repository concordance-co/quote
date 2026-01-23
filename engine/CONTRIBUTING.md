# Contributing to Quote Engine

Thank you for your interest in contributing to Quote Engine! This document provides guidelines and information for contributors.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Pull Request Process](#pull-request-process)
- [Code Style](#code-style)
- [Testing](#testing)
- [Documentation](#documentation)
- [Community](#community)

## Code of Conduct

This project adheres to a Code of Conduct that all contributors are expected to follow. Please read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before contributing.

## Getting Started

### Prerequisites

- Python 3.13 or higher
- [uv](https://github.com/astral-sh/uv) package manager
- Git

### Development Setup

1. **Fork and clone the repository**

   ```bash
   git clone https://github.com/YOUR_USERNAME/concordance-v1.git
   cd concordance-v1/engine
   ```

2. **Install dependencies**

   ```bash
   uv sync
   ```

3. **Install packages in development mode**

   ```bash
   uv pip install -e shared
   uv pip install -e sdk
   uv pip install -e inference
   ```

4. **Verify your setup**

   ```bash
   uv run pytest tests/
   ```

## How to Contribute

### Reporting Bugs

Before submitting a bug report:

1. Check the [existing issues](https://github.com/concordance-co/concordance-v1/issues) to avoid duplicates
2. Ensure you're using the latest version
3. Collect relevant information (Python version, OS, error messages, logs)

When submitting a bug report, please include:

- A clear, descriptive title
- Steps to reproduce the issue
- Expected behavior vs actual behavior
- Code samples or minimal reproduction case
- Environment details (Python version, OS, relevant package versions)
- Any relevant log output

### Suggesting Features

Feature requests are welcome! When suggesting a feature:

1. Check existing issues and discussions for similar requests
2. Clearly describe the problem your feature would solve
3. Explain your proposed solution
4. Consider alternatives you've thought about
5. If possible, outline how you might implement it

### Contributing Code

1. **Find an issue to work on** or create one for discussion
2. **Comment on the issue** to let others know you're working on it
3. **Create a branch** from `main` with a descriptive name:
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/issue-description
   ```
4. **Make your changes** following our code style guidelines
5. **Write or update tests** as needed
6. **Update documentation** if applicable
7. **Submit a pull request**

## Pull Request Process

### Before Submitting

- [ ] All tests pass locally (`uv run pytest`)
- [ ] Code follows project style guidelines
- [ ] New code has appropriate test coverage
- [ ] Documentation is updated if needed
- [ ] Commit messages follow our format
- [ ] Branch is up to date with `main`

### PR Title Format

Use a clear, descriptive title:

```
type: brief description

Examples:
feat: add backtrack support for Added events
fix: resolve KV cache corruption on multi-request batch
docs: improve mod authoring guide
refactor: extract helper functions from execute_impl
test: add unit tests for FlowEngine
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `refactor`: Code change that neither fixes a bug nor adds a feature
- `test`: Adding or updating tests
- `chore`: Maintenance tasks, dependency updates

### Review Process

1. All PRs require at least one review from a maintainer
2. Address review feedback by pushing additional commits
3. Once approved, a maintainer will merge your PR
4. Delete your branch after merge

## Code Style

### Python Style

We follow [PEP 8](https://pep8.org/) with some additions:

- **Line length**: 100 characters maximum
- **Quotes**: Double quotes for strings
- **Imports**: Sorted with `isort`, grouped (stdlib, third-party, local)
- **Type hints**: Required for public APIs, encouraged elsewhere

### Formatting Tools

```bash
# Format code
uv run black .
uv run isort .

# Check for issues
uv run ruff check .
```

### Naming Conventions

- `snake_case` for functions, variables, and module names
- `PascalCase` for class names
- `UPPER_SNAKE_CASE` for constants
- `_leading_underscore` for private/internal items

### Docstrings

Use Google-style docstrings for public APIs:

```python
def force_tokens(self, tokens: Iterable[int]) -> ModAction:
    """Force specific tokens to be emitted next.
    
    Args:
        tokens: Token IDs to force into the generation.
        
    Returns:
        A ForceTokens action that will emit the specified tokens.
        
    Raises:
        InvalidActionError: If called from an event that doesn't support this action.
        
    Example:
        >>> tokens = tokenizer.encode("Hello", add_special_tokens=False)
        >>> return actions.force_tokens(tokens)
    """
```

### Logging

Use the `logging` module instead of `print()`:

```python
import logging

logger = logging.getLogger(__name__)

# Good
logger.debug("Processing request %s", request_id)
logger.warning("Invalid token type: %s", type(token))
logger.error("Failed to encode: %s", e, exc_info=True)

# Bad
print(f"Processing request {request_id}")
print("WARNING:", error)
```

## Testing

### Running Tests

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/mod_unit_tests/forward_pass/test_force_tokens.py

# Run with coverage
uv run pytest --cov=quote --cov=quote_mod_sdk

# Run with verbose output
uv run pytest -v
```

### Writing Tests

- Place tests in the appropriate `tests/` subdirectory
- Name test files `test_*.py`
- Name test functions `test_*`
- Use descriptive names that explain what's being tested
- Include both positive and negative test cases
- Mock external dependencies when appropriate

Example test:

```python
import pytest
from quote_mod_sdk import ActionBuilder, ForwardPass
from shared.types import ForceTokens

def test_force_tokens_returns_correct_action():
    """force_tokens should return a ForceTokens action with the given tokens."""
    event = ForwardPass(request_id="test", step=0, logits=None)
    builder = ActionBuilder(event)
    
    tokens = [1, 2, 3]
    action = builder.force_tokens(tokens)
    
    assert isinstance(action, ForceTokens)
    assert action.tokens == [1, 2, 3]

def test_force_tokens_rejects_invalid_event():
    """force_tokens should raise InvalidActionError for Prefilled events."""
    from quote_mod_sdk.actions import InvalidActionError
    from shared.types import Prefilled
    
    event = Prefilled(request_id="test", step=0, max_steps=10, context_info=None)
    builder = ActionBuilder(event)
    
    with pytest.raises(InvalidActionError):
        builder.force_tokens([1, 2, 3])
```

### Test Coverage

- New features should include tests
- Bug fixes should include regression tests
- Aim for meaningful coverage, not just high percentages
- Critical paths (execute loop, mod dispatch) should have thorough coverage

## Documentation

### When to Update Documentation

- Adding new features or APIs
- Changing existing behavior
- Fixing documentation bugs
- Improving clarity or examples

### Documentation Locations

| Content | Location |
|---------|----------|
| API reference | Docstrings in code |
| Usage guides | `README.md` files |
| Mod authoring | `examples/BUILDING_TOKEN_INJECTION_MODS.md` |
| Architecture | (future) `ARCHITECTURE.md` |

### Writing Good Documentation

- Use clear, concise language
- Include code examples
- Explain the "why", not just the "what"
- Keep examples up to date with the code
- Test code examples to ensure they work

## Community

### Getting Help

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: Questions and general discussion
- **Documentation**: Check READMEs and guides first

### Recognition

Contributors will be recognized in:
- Release notes for significant contributions
- The project's contributors list

## Questions?

If you have questions about contributing that aren't answered here, please open an issue or start a discussion. We're happy to help!

---

Thank you for contributing to Quote Engine! 🎉
