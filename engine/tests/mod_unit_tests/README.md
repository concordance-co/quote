# Mod Unit Tests

Pytest-based unit tests for Concordance mod event primitives.

## Overview

This test suite validates mod behavior across all event types:

- **Prefilled**: Tests mods during initial prompt processing
- **ForwardPass**: Tests mods during forward pass computation
- **Added**: Tests mods after tokens are added to the sequence
- **Sampled**: Tests mods after token sampling

Each test validates that mods correctly implement their expected actions (noop, adjust_prefill, force_output, tool_calls, force_tokens, backtrack, adjust_logits, etc.).

## Directory Structure

```
mod_unit_tests/
├── README.md              # This file
├── pytest.ini             # Pytest configuration
├── conftest.py           # Pytest fixtures and utilities
├── test_mods.py          # Main test file
├── prefilled/            # Prefilled event tests
│   ├── test_noop.py
│   ├── test_adjust_prefill.py
│   ├── test_force_output.py
│   └── test_tool_calls.py
├── forward_pass/         # ForwardPass event tests
│   ├── test_noop.py
│   ├── test_force_tokens.py
│   ├── test_backtrack.py
│   ├── test_adjust_logits.py
│   ├── test_force_output.py
│   └── test_tool_calls.py
├── added/                # Added event tests
│   ├── test_noop.py
│   ├── test_force_tokens.py
│   ├── test_backtrack.py
│   ├── test_force_output.py
│   └── test_tool_calls.py
└── sampled/              # Sampled event tests
    ├── test_noop.py
    ├── test_force_tokens.py
    ├── test_backtrack.py
    ├── test_force_output.py
    └── test_tool_calls.py
```

## Setup and Installation

### Prerequisites

- Python 3.13+ (as required by the inference engine)
- `uv` package manager (used by Concordance)
- A properly set up virtual environment

### Quick Setup

**Using the existing venv (recommended):**

The project uses `uv` and has pytest already installed in the venv:

```bash
cd engine/tests/mod_unit_tests
../../.venv/bin/python -m pytest
```

**Or use the test runner:**

```bash
python3 run_tests.py
```

### Manual Installation

The project already has dev dependencies installed via `uv`. If you need to reinstall:

```bash
# From the engine directory
cd engine/inference
uv pip install -e ".[dev]"
```

This will install:
- pytest (>=8.3.0)
- pytest-asyncio
- httpx
- And other dev dependencies

### Verifying Installation

Check that pytest is available in the venv:

```bash
../../.venv/bin/python -m pytest --version
```

You should see output like: `pytest 8.4.2`

### Dependencies

The test suite requires:
- **pytest** (>=8.3.0): Core testing framework
- **pytest-cov** (optional): For coverage reports
- **pytest-xdist** (optional): For parallel test execution

These packages are defined in `engine/inference/pyproject.toml` under `[project.optional-dependencies]`.

## Running Tests

### Run All Tests

**Using venv pytest (recommended):**
```bash
cd engine/tests/mod_unit_tests
../../.venv/bin/python -m pytest
```

**Using Python runner:**
```bash
cd engine/tests/mod_unit_tests
python3 run_tests.py
```

**Using bash script:**
```bash
cd engine/tests/mod_unit_tests
./run_tests.sh
```

### Run Tests for Specific Event Type

**Using venv pytest:**
```bash
../../.venv/bin/python -m pytest -k "prefilled"
../../.venv/bin/python -m pytest -k "added"
```

**Using Python runner:**
```bash
python3 run_tests.py --prefilled
python3 run_tests.py --forward-pass
python3 run_tests.py --added
python3 run_tests.py --sampled
```

### Run Specific Test

**Using venv pytest:**
```bash
# Test specific mod
../../.venv/bin/python -m pytest test_mods.py::TestModPrimitives::test_mod_execution[prefilled/test_noop]

# Test force_tokens across all event types
../../.venv/bin/python -m pytest -k "force_tokens"
```

**Using Python runner:**
```bash
python3 run_tests.py -k "force_tokens"
python3 run_tests.py -k "test_noop"
```
</text>

<old_text line=76>
### Run with Verbose Output

```bash
../../.venv/bin/python -m pytest -v
```

### Run with Verbose Output

```bash
pytest -v
```

### Run with Detailed Output

**Using Python runner:**
```bash
python3 run_tests.py -vv --tb long
```

**Using venv pytest:**
```bash
../../.venv/bin/python -m pytest -vv --tb=long
```

### Run Integration Tests Only

**Using Python runner:**
```bash
python3 run_tests.py --integration
```

**Using venv pytest:**
```bash
../../.venv/bin/python -m pytest -k "integration"
```

### Run with Coverage

**Using Python runner:**
```bash
python3 run_tests.py --cov
```

**Using venv pytest:**
```bash
../../.venv/bin/python -m pytest --cov=. --cov-report=html --cov-report=term
```

### Run Tests in Parallel

**Using Python runner:**
```bash
python3 run_tests.py --parallel
```

**Using venv pytest:**
```bash
../../.venv/bin/python -m pytest -n auto
```

## Test Output

The test output shows:

```
tests/mod_unit_tests/test_mods.py::TestModPrimitives::test_mod_execution[prefilled/test_noop] PASSED
test_mods.py::TestModPrimitives::test_mod_execution[prefilled/test_noop] PASSED
test_mods.py::TestModPrimitives::test_mod_execution[prefilled/test_adjust_prefill] PASSED
test_mods.py::TestModPrimitives::test_mod_execution[prefilled/test_force_output] PASSED
...

======================== test summary info =========================
17 passed, 6 skipped in 0.04s
```

## How Tests Work

### 1. Test Discovery

The `conftest.py` automatically discovers all `test_*.py` files in event type directories and parametrizes tests to run for each mod.

### 2. Mod Loading

Each mod file is dynamically loaded and its `@mod` decorated function is extracted.

### 3. Event Creation

Based on the event type, an appropriate event is created:
- **Prefilled**: Uses the test prompt (e.g., "Say hello to me")
- **ForwardPass**: Creates forward pass with prompt tokens
- **Added**: Simulates tokens being added
- **Sampled**: Simulates a sampled token

### 4. Action Validation

The mod is executed with the event, and the returned action is validated:
- Action type matches expectations
- Action contains required data (tokens, text, etc.)
- Stateful mods maintain state correctly

## Writing New Tests

### 1. Create Mod File

Create a new file in the appropriate event directory:

```python
# added/test_my_feature.py
"""Test description of what this mod does."""

from quote_mod_sdk import mod, Added

@mod
def test_added_my_feature(event, actions, tokenizer):
    """Mod implementation."""
    if isinstance(event, Added):
        # Your mod logic here
        text = tokenizer.decode(event.added_tokens)
        if "trigger" in text:
            return actions.force_output("Response!")
    
    return actions.noop()
```

### 2. Add Test Configuration

Update `TEST_CONFIGS` in `test_mods.py`:

```python
"added": {
    # ... existing tests ...
    "test_my_feature": {
        "prompt": "Say trigger word",
        "expected_action": ForceOutput,
        "description": "Should force output on trigger",
    },
}
```

### 3. Run Your Test

```bash
pytest -k "test_my_feature"
```

## Test Fixtures

### Available Fixtures

- **`tokenizer`**: Simple character-level tokenizer for testing
- **`mod_context`**: Factory for creating mod test contexts
- **`validator`**: Utilities for validating action types

### Event Creators

Helper functions to create events:

```python
from conftest import (
    create_prefilled_event,
    create_forward_pass_event,
    create_added_event,
    create_sampled_event,
)

# Create events for testing
event = create_prefilled_event(
    request_id="test_req",
    prompt="Test prompt",
    tokenizer=tokenizer,
    step=0
)
```

## Stateful Mods

Some mods maintain state across events and need multiple events before they trigger their actions. The test system automatically handles these by:

1. **Detecting state requirements**: Tests are configured with `needs_multiple_events` or `needs_added_events`
2. **Sending multiple events**: Automatically sends the required number of events to build up state
3. **Validating at the right time**: Checks that actions trigger after the correct number of events

### Examples of Stateful Mods

- **`sampled/test_backtrack`**: Needs 3 Sampled events before backtracking
- **`sampled/test_force_output`**: Needs 5 Sampled events before forcing output
- **`sampled/test_tool_calls`**: Needs 2 Sampled events before triggering tool call
- **`forward_pass/test_backtrack`**: Needs 5 Added events to count tokens before backtracking
- **`forward_pass/test_force_output`**: Needs 3 Added events to count tokens before forcing output
- **`added/test_force_tokens`**: Tracks accumulated text across Added events

### How It Works

The test configuration specifies event requirements:

```python
"sampled": {
    "test_backtrack": {
        "prompt": "Count slowly.",
        "expected_action": Backtrack,
        "needs_multiple_events": 3,  # Sends 3 Sampled events
    },
}
```

The test automatically:
1. Creates and sends 3 Sampled events with the same request_id
2. Executes the mod for each event to build state
3. Validates that the final event returns a Backtrack action

## Debugging Failed Tests

### 1. Run Single Test with Verbose Output

```bash
pytest test_mods.py::TestModPrimitives::test_mod_execution[added/test_force_tokens] -vv
```

### 2. Add Print Statements

Mod print statements are captured by pytest:

```python
@mod
def test_added_my_feature(event, actions, tokenizer):
    print(f"Event: {event}")  # Will show in pytest output on failure
    if isinstance(event, Added):
        text = tokenizer.decode(event.added_tokens)
        print(f"Decoded text: {text}")
        # ...
```

### 3. Run with PDB

```bash
pytest --pdb  # Drop into debugger on failure
```

## Integration with CI/CD

Add to your CI pipeline:

```yaml
- name: Run Mod Unit Tests
  run: |
    cd engine/tests/mod_unit_tests
    pytest --junitxml=test-results.xml
```

## Advantages Over Old Test Runner

1. **Standard pytest**: Uses familiar pytest conventions
2. **Better isolation**: Each test runs independently
3. **Parametrization**: Automatically discovers and runs all mods
4. **Fixtures**: Reusable test components
5. **Better reporting**: Clear pass/fail with detailed errors
6. **No server required**: Tests mods directly without HTTP overhead
7. **Faster**: No network latency or server startup time
8. **IDE integration**: Works with pytest plugins in VS Code, PyCharm, etc.
9. **Parallel execution**: Can run tests in parallel with `pytest-xdist`
10. **Coverage**: Easy to integrate with `pytest-cov`

## Advanced Usage

### Running with Coverage

**Automatic (recommended):**
```bash
python3 run_tests.py --cov
```

**Manual:**
```bash
# Install pytest-cov if needed (via uv)
cd ../../inference
uv pip install pytest-cov

# Run with coverage
cd ../tests/mod_unit_tests
../../.venv/bin/python -m pytest --cov=. --cov-report=html
```

### Parallel Execution

**Automatic (recommended):**
```bash
python3 run_tests.py --parallel
```

**Manual:**
```bash
# Install pytest-xdist if needed (via uv)
cd ../../inference
uv pip install pytest-xdist

# Run tests in parallel
cd ../tests/mod_unit_tests
../../.venv/bin/python -m pytest -n auto
```

### Debugging

Drop into debugger on test failure:
```bash
python3 run_tests.py --pdb
```

Or with venv pytest:
```bash
../../.venv/bin/python -m pytest --pdb
```

## Troubleshooting

### Import Mismatch Errors

If you see errors like "import file mismatch" or "imported module has different __file__ attribute":

```bash
# Clean cache files
cd engine/tests/mod_unit_tests
make clean

# Or manually
rm -rf .pytest_cache __pycache__
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
```

Then run tests again.

### Import Errors

If you see import errors, ensure you're in the correct directory and using the venv:

```bash
cd engine/tests/mod_unit_tests
../../.venv/bin/python -m pytest
```

### Mod Not Found

If a mod isn't discovered, verify:
1. File is named `test_*.py`
2. File is in an event type directory (prefilled, forward_pass, added, sampled)
3. File contains a function decorated with `@mod`

### Action Type Mismatch

If a test expects a specific action but gets Noop:
1. Check if the mod's trigger conditions are met
2. Verify the test configuration provides the right prompt/input
3. Add debug prints to see what the mod is receiving

## Future Enhancements

- [ ] Add property-based testing with Hypothesis
- [ ] Add benchmarking for mod performance
- [ ] Add mutation testing
- [ ] Generate test reports with metrics
- [ ] Add visual diff for token sequences