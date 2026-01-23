# Migration Guide: From HTTP Test Runner to Pytest

This guide helps you transition from the old HTTP-based test runner to the new pytest-based test system.

## Overview of Changes

### Old System (Deprecated)

The previous test system (`src/test_runner.py`) worked by:

1. Starting/connecting to a local HTTP server
2. Uploading mods via HTTP API
3. Sending chat completion requests to test mods
4. Parsing HTTP responses to validate behavior
5. Manual test configuration in Python code

**Key characteristics:**
- Required running server
- HTTP overhead for each test
- Network-dependent
- Slower execution
- Manual test discovery and validation
- Tight coupling to server implementation

### New System (Current)

The new pytest-based system works by:

1. Loading mods directly from Python files
2. Creating events programmatically
3. Executing mods in-process with test events
4. Validating mod actions directly
5. Using pytest's parametrization for automatic test discovery

**Key characteristics:**
- No server required
- Direct function calls (fast)
- Pure unit testing
- Parallel execution support
- Automatic test discovery
- IDE integration
- Better debugging

## Why We Migrated

### Problems with Old Approach

1. **Slow**: HTTP round-trips added significant overhead
2. **Brittle**: Depended on server being properly configured
3. **Limited debugging**: Hard to step through mod execution
4. **Manual configuration**: Each test required explicit setup
5. **No parallelization**: Tests ran sequentially
6. **Hard to maintain**: Test configuration scattered across multiple methods

### Benefits of New Approach

1. **Fast**: Direct function calls, no network overhead
2. **Isolated**: Each test runs in clean environment
3. **Easy debugging**: Can use PDB, print statements, IDE debuggers
4. **Automatic**: Tests auto-discovered from file structure
5. **Parallel**: Can run tests concurrently
6. **Standard**: Uses pytest conventions familiar to Python developers
7. **Better reports**: Clear pass/fail with detailed error messages
8. **CI/CD friendly**: Easier to integrate into pipelines

## Quick Start with New System

### Installation

```bash
cd engine/tests/mod_unit_tests
python3 run_tests.py --install
```

### Running Tests

```bash
# Run all tests
make test

# Or directly
python3 run_tests.py

# Run specific event type
python3 run_tests.py --prefilled

# Run with coverage
python3 run_tests.py --cov
```

## Side-by-Side Comparison

### Old System Usage

```bash
# Old way
cd src
python test_runner.py --base-url http://0.0.0.0:8000 --user-api-key test-key
```

**Requirements:**
- Server must be running
- Mods must be uploaded via upload script
- API key needed
- Network connectivity

### New System Usage

```bash
# New way
cd engine/tests/mod_unit_tests
make test
```

**Requirements:**
- Just Python and pytest
- No server needed
- No API keys
- No network

## File Structure Changes

### Old Structure

```
src/
├── test_runner.py          # Monolithic test runner
└── upload_mods.py          # Separate upload script

mods/unit_tests/
├── prefilled/
│   └── test_noop.py        # Mod files
└── ...
```

### New Structure

```
engine/tests/mod_unit_tests/
├── conftest.py             # Pytest fixtures
├── test_mods.py            # Test implementations
├── pytest.ini              # Configuration
├── run_tests.py            # Python runner
├── run_tests.sh            # Bash runner
├── Makefile                # Convenient shortcuts
├── README.md               # Documentation
├── MIGRATION.md            # This file
├── prefilled/
│   └── test_noop.py        # Mod files (unchanged)
└── ...
```

## Mapping Old to New

### Test Configuration

**Old System:**

```python
# In test_runner.py
configs = {
    "prefilled": {
        "test_noop": (
            "Say hello to me.",
            "Normal response",
            validate_noop
        ),
    }
}
```

**New System:**

```python
# In test_mods.py
TEST_CONFIGS = {
    "prefilled": {
        "test_noop": {
            "prompt": "Say hello to me.",
            "expected_action": Noop,
            "description": "Normal response, no modification",
        },
    }
}
```

### Running a Test

**Old System:**

```python
# HTTP request in test_runner.py
def run_test(self, mod_name: str, test_prompt: str, expected_behavior: str):
    payload = {
        "model": f"modularai/Llama-3.1-8B-Instruct-GGUF/{mod_name}",
        "messages": [{"role": "user", "content": test_prompt}],
        "user_api_key": self.user_api_key,
        "max_tokens": 50,
    }
    response = requests.post(
        f"{self.base_url}/v1/chat/completions",
        json=payload,
        timeout=60
    )
    # Parse and validate response
```

**New System:**

```python
# Direct execution in test_mods.py
def test_mod_execution(self, mod_file, tokenizer, validator):
    mod_function, mod_name = load_mod_from_file(mod_file)
    event = create_prefilled_event(
        request_id="test_req",
        prompt="Say hello to me.",
        tokenizer=tokenizer
    )
    action = mod_function(event, tokenizer)
    assert isinstance(action, Noop)
```

### Validation

**Old System:**

```python
# HTTP response validation
def validate_noop(output, message):
    return True, "Response received"

def validate_adjust_prefill(output, message):
    if output and "goodbye" in output.lower():
        return True, "Contains 'goodbye'"
    return False, f"Missing 'goodbye': {output[:100]}"
```

**New System:**

```python
# Direct action validation
def test_mod_execution(self, mod_file, tokenizer):
    # ... setup ...
    action = mod_function(event, tokenizer)
    
    # Direct type checking
    assert isinstance(action, AdjustedPrefill)
    
    # Validate action properties
    assert len(action.tokens) > 0
    decoded = tokenizer.decode(action.tokens)
    assert "goodbye" in decoded.lower()
```

## Migration Checklist

If you're migrating custom tests or adding new ones:

### 1. ✓ Verify Test Files

Your mod files should still work as-is:

```python
# This doesn't need to change
from quote_mod_sdk import mod, Prefilled

@mod
def test_prefilled_noop(event, actions, tokenizer):
    if isinstance(event, Prefilled):
        return actions.noop()
    return actions.noop()
```

### 2. ✓ Update Test Configuration

Add your test to `TEST_CONFIGS` in `test_mods.py`:

```python
TEST_CONFIGS = {
    "your_event_type": {
        "test_your_feature": {
            "prompt": "Your test prompt",
            "expected_action": ExpectedActionType,
            "description": "What this test validates",
        },
    }
}
```

### 3. ✓ Remove Old Scripts

Once migrated, you can remove:
- Old `test_runner.py`
- Old `upload_mods.py`
- Any custom HTTP client code

### 4. ✓ Update CI/CD

Update your CI pipeline:

**Old:**
```yaml
- name: Start server
  run: python local.py &
- name: Run tests
  run: python src/test_runner.py
```

**New:**
```yaml
- name: Run tests
  run: |
    cd engine/tests/mod_unit_tests
    python3 run_tests.py --install
```

### 5. ✓ Update Documentation

Update any references to the old test system in your docs.

## Common Migration Issues

### Issue: "ModuleNotFoundError: No module named 'pytest'"

**Solution:**
```bash
python3 run_tests.py --install
# or
pip install pytest
```

### Issue: "ModuleNotFoundError: No module named 'max'"

**Solution:** This is handled automatically by conftest.py. If you see this error, make sure you're running tests from the correct directory:
```bash
cd engine/tests/mod_unit_tests
pytest
```

### Issue: "Cannot find mod function in file"

**Solution:** Ensure your mod file has a function decorated with `@mod`:
```python
from quote_mod_sdk import mod, Prefilled

@mod  # This decorator is required
def test_prefilled_noop(event, actions, tokenizer):
    # ...
```

### Issue: "Test always returns Noop"

**Solution:** Your test event might not be triggering the mod's conditions. Add debug prints:
```python
@mod
def test_prefilled_adjust(event, actions, tokenizer):
    print(f"Event type: {type(event)}")  # Will show in pytest output
    if isinstance(event, Prefilled):
        prompt = tokenizer.decode(event.context_info.tokens)
        print(f"Prompt: {prompt}")  # Check what prompt the mod sees
        # ...
```

### Issue: "Can't run tests from wrong directory"

**Solution:** Always run from the test directory:
```bash
cd engine/tests/mod_unit_tests
python3 run_tests.py
```

Or use absolute paths:
```bash
python3 engine/tests/mod_unit_tests/run_tests.py
```

## Features No Longer Needed

### Server Management

**Old:** Required starting and stopping server
**New:** No server needed

### Mod Upload

**Old:** Required uploading mods via HTTP API
**New:** Mods loaded directly from files

### API Keys

**Old:** Required user API key for authentication
**New:** No authentication needed

### Network Configuration

**Old:** Required configuring base URL, ports, etc.
**New:** Pure in-process testing

## New Features Available

### Parallel Execution

```bash
python3 run_tests.py --parallel
```

### Coverage Reports

```bash
python3 run_tests.py --cov
```

### Debugger Integration

```bash
python3 run_tests.py --pdb
```

### IDE Integration

- Use pytest plugin in VS Code
- Use pytest runner in PyCharm
- Set breakpoints in your IDE
- Step through mod execution

### Watch Mode

```bash
make watch
# Tests automatically re-run when files change
```

## Performance Comparison

Based on testing with 19 mod tests:

| Metric | Old System | New System | Improvement |
|--------|-----------|------------|-------------|
| Setup time | ~5-10s (server start) | ~0s | Instant |
| Per-test time | ~0.5-2s (HTTP) | ~0.01-0.05s | 10-100x faster |
| Total time (19 tests) | ~20-40s | ~2-3s | 10x faster |
| Parallel time | N/A | ~1s | 20x faster |

## Rollback Plan

If you need to temporarily use the old system:

1. Keep the old `test_runner.py` in a backup location
2. Start your server manually
3. Run the old test runner

However, we recommend migrating fully to pytest as the old system will not be maintained.

## Getting Help

### Questions?

1. Check `README.md` for detailed usage instructions
2. Run `python3 run_tests.py --help` for options
3. Run `make help` for available commands
4. Look at existing test files for examples

### Issues?

1. Verify you're in the correct directory
2. Check that pytest is installed
3. Try running with `--install` flag
4. Look at the "Troubleshooting" section in README.md

### Contributing?

New tests follow this pattern:

1. Add mod file in appropriate event directory
2. Add test config to `TEST_CONFIGS`
3. Run tests to verify
4. Commit both files

## Summary

The migration from HTTP-based testing to pytest provides:

- ✅ **10-100x faster** test execution
- ✅ **No server dependencies** - pure unit tests
- ✅ **Better debugging** - use PDB, IDE debuggers
- ✅ **Automatic discovery** - no manual configuration
- ✅ **Parallel execution** - run tests concurrently
- ✅ **Standard tooling** - uses pytest conventions
- ✅ **CI/CD friendly** - easy integration
- ✅ **Better reports** - clear, detailed output

**Get started now:**
```bash
cd engine/tests/mod_unit_tests
python3 run_tests.py --install
```

## Feedback

If you encounter issues or have suggestions for improving the test system, please file an issue or submit a PR.