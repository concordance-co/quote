# Mod Unit Tests - Quick Reference

## Installation

```bash
# Quick install and run
cd engine/tests/mod_unit_tests
python3 run_tests.py --install

# Manual install
pip install pytest pytest-cov pytest-xdist
```

## Running Tests

### Basic Commands

```bash
# Run all tests
make test                    # Using Makefile
python3 run_tests.py         # Using Python runner
pytest                       # Using pytest directly

# Verbose output
python3 run_tests.py -v
python3 run_tests.py -vv     # Very verbose

# Quick run (minimal output)
make quick
```

### Event Type Filters

```bash
# Run tests by event type
python3 run_tests.py --prefilled
python3 run_tests.py --forward-pass
python3 run_tests.py --added
python3 run_tests.py --sampled

# Or with make
make prefilled
make added
```

### Pattern Matching

```bash
# Run tests matching pattern
python3 run_tests.py -k "force_tokens"
python3 run_tests.py -k "noop"
python3 run_tests.py -k "prefilled and force"

# With pytest
pytest -k "test_noop"
```

### Specific Tests

```bash
# Run single test
pytest test_mods.py::TestModPrimitives::test_mod_execution[prefilled/test_noop]

# Run test class
pytest test_mods.py::TestModPrimitives

# Run integration tests only
python3 run_tests.py --integration
```

## Advanced Options

### Coverage

```bash
make coverage                # Using Makefile
python3 run_tests.py --cov   # Using Python runner

# View HTML report
open htmlcov/index.html
```

### Parallel Execution

```bash
make parallel                    # Using Makefile
python3 run_tests.py --parallel  # Using Python runner
pytest -n auto                   # Using pytest
```

### Debugging

```bash
# Drop into debugger on failure
python3 run_tests.py --pdb
pytest --pdb

# Show print statements
pytest -s

# More verbose tracebacks
pytest --tb=long
```

### Watch Mode

```bash
make watch                   # Auto-rerun on file changes
```

## Common Patterns

### Adding a New Test

1. Create mod file:
   ```bash
   # e.g., added/test_my_feature.py
   ```

2. Add to TEST_CONFIGS in test_mods.py:
   ```python
   "added": {
       "test_my_feature": {
           "prompt": "Test prompt",
           "expected_action": ForceOutput,
           "description": "What it tests",
       },
   }
   ```

3. Run your test:
   ```bash
   pytest -k "test_my_feature"
   ```

### Debugging Failed Tests

```bash
# 1. Run with verbose output and full traceback
pytest -vv --tb=long -k "failing_test"

# 2. Run with debugger
pytest --pdb -k "failing_test"

# 3. Show print statements
pytest -s -k "failing_test"

# 4. Run single test with maximum detail
pytest -vv --tb=long -s test_mods.py::TestModPrimitives::test_mod_execution[prefilled/test_noop]
```

### Check Test Status

```bash
# List all tests without running
pytest --collect-only

# Show test duration
pytest --durations=10

# Show slowest tests
pytest --durations=0
```

## File Locations

```
engine/tests/mod_unit_tests/
├── conftest.py           # Fixtures and utilities
├── test_mods.py          # Test implementations
├── pytest.ini            # Pytest config
├── run_tests.py          # Python runner
├── Makefile              # Make commands
├── {event_type}/         # Event-specific mods
│   └── test_*.py         # Individual mod tests
```

## Exit Codes

- `0` - All tests passed
- `1` - Some tests failed
- `2` - Test execution interrupted
- `3` - Internal pytest error
- `4` - pytest command line usage error
- `5` - No tests collected

## Environment Variables

```bash
# Pytest options
export PYTEST_ADDOPTS="-v --tb=short"

# Disable color
export NO_COLOR=1

# Python path (if needed)
export PYTHONPATH="../../inference/src:../../sdk:../../shared/src"
```

## Useful Aliases

Add to your shell config:

```bash
# ~/.bashrc or ~/.zshrc
alias mt='cd engine/tests/mod_unit_tests && make test'
alias mtv='cd engine/tests/mod_unit_tests && pytest -vv'
alias mtc='cd engine/tests/mod_unit_tests && make coverage'
alias mtp='cd engine/tests/mod_unit_tests && make parallel'
```

## Common Issues

| Issue | Solution |
|-------|----------|
| `pytest not found` | Run `python3 run_tests.py --install` |
| `ModuleNotFoundError: max` | Run from test directory: `cd engine/tests/mod_unit_tests` |
| `No tests collected` | Check file naming: `test_*.py` |
| `Import errors` | Verify you're in `engine/tests/mod_unit_tests` |
| `Slow tests` | Use `--parallel` flag |

## Pytest Markers

```bash
# Run marked tests
pytest -m prefilled
pytest -m integration

# List available markers
pytest --markers
```

## CI/CD Integration

```yaml
# .github/workflows/test.yml
- name: Run Mod Tests
  run: |
    cd engine/tests/mod_unit_tests
    python3 run_tests.py --install --parallel --cov
```

## Quick Examples

```bash
# Most common: Run all tests with coverage
make coverage

# Debug a failing test
pytest --pdb -k "test_force_tokens"

# Run tests for one event type
make prefilled

# Fast parallel execution
make parallel

# Continuous testing during development
make watch
```

## Help Commands

```bash
python3 run_tests.py --help    # Python runner help
pytest --help                  # Pytest help
make help                      # Makefile help
```

## Performance Tips

1. **Parallel execution** - Use `-n auto` for faster runs
2. **Selective testing** - Use `-k` to run only relevant tests
3. **Quiet mode** - Use `-q` for less output
4. **Fail fast** - Use `-x` to stop on first failure
5. **Last failed** - Use `--lf` to re-run only failed tests

```bash
# Fast feedback loop
pytest -x --lf -n auto
```

## Documentation

- **README.md** - Full documentation
- **MIGRATION.md** - Migration from old system
- **QUICKREF.md** - This file
- **pytest.ini** - Configuration details

---

**Quick Start:**
```bash
cd engine/tests/mod_unit_tests && python3 run_tests.py --install
```
