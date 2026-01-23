# Open Source Preparation Plan

This document outlines the tasks required to prepare the Concordance engine repository for open source release.

---

## Table of Contents

1. [Required Open Source Files](#1-required-open-source-files)
2. [License Review](#2-license-review)
3. [Dead Code & Backup Files](#3-dead-code--backup-files)
4. [Debug Print Statements](#4-debug-print-statements)
5. [TODO/FIXME Comments](#5-todofixme-comments)
6. [Documentation Improvements](#6-documentation-improvements)
7. [Security Review](#7-security-review)
8. [Code Quality](#8-code-quality)
9. [Testing](#9-testing)
10. [Repository Cleanup](#10-repository-cleanup)
11. [CI/CD & Automation](#11-cicd--automation)
12. [Pre-Release Checklist](#12-pre-release-checklist)

---

## 1. Required Open Source Files

### Missing Files (Must Create)

| File | Purpose | Priority |
|------|---------|----------|
| `README.md` | Root project overview, quickstart, badges | ✅ Done |
| `CONTRIBUTING.md` | Contribution guidelines, PR process, code style | ✅ Done |
| `CODE_OF_CONDUCT.md` | Community behavior standards | ✅ Done |
| `CHANGELOG.md` | Version history and release notes | ✅ Done |
| `SECURITY.md` | Security policy, vulnerability reporting | ✅ Done |
| `.github/ISSUE_TEMPLATE/` | Bug report, feature request templates | ✅ Done |
| `.github/PULL_REQUEST_TEMPLATE.md` | PR checklist template | ✅ Done |
| `ARCHITECTURE.md` | High-level system architecture overview | 🟢 Medium |

### Actions

- [x] Create root `README.md` with: ✅ DONE
  - Project description and value proposition
  - Installation instructions
  - Quick start example
  - Links to sub-package READMEs
  - Badge for CI status, license, Python version
- [x] Create `CONTRIBUTING.md` covering: ✅ DONE
  - Development environment setup
  - Code style guidelines
  - Testing requirements
  - PR review process
- [x] Create `CODE_OF_CONDUCT.md` (recommend Contributor Covenant) ✅ DONE
- [x] Create `SECURITY.md` with vulnerability disclosure process ✅ DONE
- [x] Create `CHANGELOG.md` (consider using Keep a Changelog format) ✅ DONE

---

## 2. License Review

### Current State

The current license in `inference/LICENSE`, `sdk/LICENSE`, and `shared/LICENSE` is an **Alpha Evaluation License** that:
- Prohibits production/commercial use
- Prohibits distribution
- Prohibits modification
- Is time-limited

### Actions

- [ ] **Choose an open source license** (recommendations: Apache 2.0, MIT, or GPL v3)
- [ ] Update `LICENSE` files in all sub-packages
- [ ] Add root-level `LICENSE` file
- [ ] Add license headers to all source files (optional but recommended)
- [ ] Update `pyproject.toml` files with correct license metadata
- [ ] Review third-party dependencies for license compatibility

### Files Requiring License Updates

```
engine/inference/LICENSE
engine/sdk/LICENSE
engine/shared/LICENSE
engine/inference/pyproject.toml  # description says "Add your description here"
```

---

## 3. Dead Code & Backup Files

### Files to Delete

| Path | Reason |
|------|--------|
| `inference/src/quote/hot/backups/execute_impl.backup.20250910-110535.py` | Development backup |
| `inference/src/quote/hot/backups/execute_impl.backup.20250910-110901.py` | Development backup |
| `sdk/quote_mod_sdk/.mods_registry.json` | Local dev state (hardcoded embedding URL) |

### Directories to Verify/Clean

| Path | Action |
|------|--------|
| `inference/src/quote/hot/backups/` | Delete entire directory or add to `.gitignore` |
| `sdk/quote_mod_sdk/__pycache__/` | Should be gitignored |
| `sdk/__pycache__/` | Should be gitignored |
| `sdk/quote_mod_sdk.egg-info/` | Should be gitignored |
| `tests/**/__pycache__/` | Should be gitignored |
| `.pytest_cache/` directories | Should be gitignored |

### Actions

- [x] Delete backup files in `inference/src/quote/hot/backups/` ✅ DONE
- [x] Delete or gitignore `.mods_registry.json` ✅ DONE
- [x] Verify `.gitignore` covers all build artifacts ✅ DONE (expanded with IDE, testing, build patterns)
- [ ] Run `git clean -fXd --dry-run` to identify untracked files

---

## 4. Debug Print Statements

### High Priority (Production Code)

| File | Lines | Issue |
|------|-------|-------|
| `inference/src/quote/hot/execute_impl.py` | ~714-717 | `print("WARNING: Invalid type in action logits")` |
| `inference/src/quote/hot/execute_impl.py` | ~502-505 | `print(f"[mods][AdjustedPrefill] Failed...")` |
| `inference/src/quote/hot/execute_impl.py` | ~339-340 | `print(f"[mods] ToolCalls encode failed...")` |
| `inference/src/quote/mods/manager.py` | ~115-119 | `print()` in Backtrack action logging |

### Medium Priority (Examples - May Keep for Demos)

| File | Issue |
|------|-------|
| `examples/demos/mods.py` | `print()` in `backtrack_demo` |
| `examples/json_schema/mod.py` | Multiple debug prints throughout |
| `examples/tau2/mod.py` | `print("convo", get_conversation())` |
| `examples/tau2/prompts.py` | Multiple `print()` calls |

### Actions

- [x] Replace production `print()` with proper logging (`logging.warning()`, `logging.debug()`) ✅ DONE
- [x] Review example print statements - decide if they serve educational purpose ✅ DONE (converted to logging)
- [ ] Configure logging levels appropriately
- [ ] Consider adding a debug flag/environment variable for verbose output

---

## 5. TODO/FIXME Comments

### Must Address Before Release

| File | Line | Comment |
|------|------|---------|
| `inference/src/quote/custom_arch/gemma3/layers/transformer_block.py` | ~52-62 | `TODO: Figure out a better way to indicate to the type checker...` |
| `inference/src/quote/pipelines/text_gen_pipeline.py` | ~120-127 | `TODO: This should be removed.` (eos_token_id) |
| `inference/src/quote/pipelines/text_gen_pipeline.py` | ~200-204 | `TODO: These should ideally not call _weights_repo_id directly...` |

### Document or Remove

| File | Issue |
|------|-------|
| `inference/src/quote/hot/backups/*.py` | Multiple `[TODO]` comments for unimplemented features (Backtrack KV rewind) |

### Actions

- [ ] Address or document each TODO comment
- [ ] Remove stale TODOs that are no longer relevant
- [ ] Convert important TODOs to GitHub issues after open sourcing
- [ ] Add `# TODO(username):` format for tracking ownership

---

## 6. Documentation Improvements

### Sub-Package READMEs

| File | Current State | Needs |
|------|---------------|-------|
| `inference/README.md` | Comprehensive | Review for sensitive URLs, add API reference |
| `sdk/README.md` | Good | Add more examples, installation from PyPI |
| `shared/README.md` | ✅ Complete | Added description of types, events, actions, conversation API |
| `tests/mod_unit_tests/README.md` | Exists | Review and update |

### Documentation Gaps

- [x] `shared/README.md` is empty - needs content ✅ DONE
- [ ] No API reference documentation
- [ ] No architecture diagram
- [ ] Example code comments could be more thorough

### Actions

- [ ] Write content for `shared/README.md`
- [ ] Add docstrings to public APIs in SDK
- [ ] Consider adding Sphinx/MkDocs for API documentation
- [ ] Create architecture diagram showing component relationships
- [ ] Review and update `BUILDING_TOKEN_INJECTION_MODS.md` for accuracy

---

## 7. Security Review

### Sensitive Data Check

| Item | Location | Action |
|------|----------|--------|
| Hardcoded URLs | `inference/README.md` | Contains Modal deployment URLs - review if these should be examples |
| API key references | `sdk/quote_mod_sdk/.mods_registry.json` | Contains localhost embedding URL - delete file |
| Modal app names | `inference/README.md` | `concordance--max-openai-compatible...` - anonymize or document |
| `.servers` file reference | `inference/README.md` | Document that this is gitignored |

### Actions

- [ ] Grep for hardcoded credentials, API keys, tokens
- [ ] Review all URLs for internal/sensitive endpoints
- [ ] Ensure `.env` files are properly gitignored
- [ ] Add `.servers` to root `.gitignore` if not present
- [ ] Document environment variable requirements
- [ ] Review Modal deployment configuration for sensitive data

### Command to Run

```bash
# Search for potential secrets
grep -rn "password\|secret\|api.key\|token\|credential" --include="*.py" --include="*.json" --include="*.yaml"
```

---

## 8. Code Quality

### Style Consistency

- [ ] Add `pyproject.toml` configuration for:
  - `black` (code formatting)
  - `isort` (import sorting)
  - `ruff` or `flake8` (linting)
  - `mypy` (type checking)
- [ ] Run formatters across entire codebase
- [ ] Add pre-commit hooks configuration (`.pre-commit-config.yaml`)

### Type Hints

Files with incomplete type hints:
- `sdk/quote_mod_sdk/flow.py` - has some `Any` types that could be more specific
- `examples/` - examples should model best practices

### Actions

- [ ] Configure and run `black` formatter
- [ ] Configure and run `isort`
- [ ] Add `ruff` or `flake8` configuration
- [ ] Run `mypy` and address critical type errors
- [ ] Create `.pre-commit-config.yaml`

---

## 9. Testing

### Current Test Structure

```
tests/
├── inference/
│   └── integration/
├── mod_trace/
├── mod_unit_tests/
│   ├── added/
│   ├── forward_pass/
│   ├── prefilled/
│   └── sampled/
├── sdk/
└── server/
```

### Actions

- [ ] Verify all tests pass: `uv run pytest`
- [ ] Check test coverage: `uv run pytest --cov`
- [ ] Add missing tests for public SDK APIs
- [ ] Document how to run tests in `CONTRIBUTING.md`
- [ ] Add GitHub Actions workflow for CI

---

## 10. Repository Cleanup

### .gitignore Audit

Current `.gitignore` covers:
- Python artifacts (`__pycache__/`, `*.py[oc]`, etc.)
- Virtual environments (`.venv`)
- Build artifacts
- Logs directories
- IDE files (`.DS_Store`)

### Missing from .gitignore (Verify)

```
# IDE
.idea/
.vscode/
*.swp
*.swo

# Testing
.coverage
htmlcov/
.hypothesis/

# Build
*.egg
*.whl

# Environment
.env.local
.env.*.local
```

### Actions

- [ ] Audit and update `.gitignore`
- [ ] Remove any committed files that should be ignored
- [ ] Consider adding `.dockerignore` if Docker is used

---

## 11. CI/CD & Automation

### GitHub Actions Workflows to Create

| Workflow | Purpose |
|----------|---------|
| `ci.yml` | Run tests, linting on PRs |
| `release.yml` | Publish to PyPI on tags |
| `docs.yml` | Build and deploy documentation |

### Example CI Workflow

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync
      - run: uv run pytest
      - run: uv run ruff check .
```

### Actions

- [ ] Create `.github/workflows/ci.yml`
- [ ] Configure branch protection rules
- [ ] Set up automated release workflow
- [ ] Consider adding CodeQL security scanning

---

## 12. Pre-Release Checklist

### Final Review

- [ ] All tests pass
- [ ] No sensitive data in repository
- [ ] License files are correct
- [ ] README is complete and accurate
- [ ] CONTRIBUTING guide is complete
- [ ] All TODO comments addressed or converted to issues
- [ ] Debug print statements removed/converted to logging
- [ ] Dead code and backup files removed
- [ ] `.gitignore` is comprehensive
- [ ] CI/CD workflows are functional
- [ ] Package metadata (`pyproject.toml`) is complete
- [ ] Version numbers are consistent across packages

### Repository Settings (Post-Open Source)

- [ ] Enable GitHub Discussions
- [ ] Configure issue labels
- [ ] Set up branch protection for `main`
- [ ] Enable vulnerability alerts
- [ ] Configure Dependabot for dependency updates

### Announcement Preparation

- [ ] Write announcement blog post / tweet
- [ ] Prepare demo video or GIF
- [ ] Identify relevant communities to share with
- [ ] Plan for handling initial issues/questions

---

## Priority Order

### Phase 1 - Critical (Before Any Public Visibility)
1. Update licenses
2. ~~Remove sensitive data~~ ✅ DONE
3. ~~Create root README.md~~ ✅ DONE
4. ~~Remove backup files and dead code~~ ✅ DONE

### Phase 2 - High (Before Announcement)
1. ~~Create CONTRIBUTING.md and CODE_OF_CONDUCT.md~~ ✅ DONE
2. ~~Clean up debug print statements~~ ✅ DONE
3. Address critical TODOs
4. ~~Set up CI/CD~~ ✅ DONE

### Phase 3 - Medium (First Week After Release)
1. ~~Improve documentation~~ ✅ DONE (README, CONTRIBUTING, SECURITY, CHANGELOG)
2. ~~Add issue/PR templates~~ ✅ DONE
3. ~~Configure code quality tools~~ ✅ DONE (CI workflow with ruff, black, isort, mypy)
4. Expand test coverage

### Phase 4 - Ongoing
1. Respond to community feedback
2. Address filed issues
3. Iterate on documentation based on questions

---

## Completed Actions Summary

The following cleanup tasks have been completed:

| Task | Status |
|------|--------|
| Replace `print()` with `logging` in `execute_impl.py` | ✅ Done |
| Replace `print()` with `logging` in `local.py` | ✅ Done |
| Remove API key logging from `local.py` | ✅ Done |
| Delete backup files (`hot/backups/`) | ✅ Done |
| Delete `.mods_registry.json` | ✅ Done |
| Update `.gitignore` with comprehensive patterns | ✅ Done |
| Extract `_extract_user_api_key()` helper function | ✅ Done |
| Replace `print()` in `examples/json_schema/mod.py` | ✅ Done |
| Replace `print()` in `examples/tau2/mod.py` | ✅ Done |
| Replace `print()` in `examples/tau2/prompts.py` | ✅ Done |
| Replace `print()` in `examples/demos/mods.py` | ✅ Done |
| Update `inference/pyproject.toml` description | ✅ Done |
| Write content for `shared/README.md` | ✅ Done |
| Create root `README.md` | ✅ Done |
| Create `CONTRIBUTING.md` | ✅ Done |
| Create `CODE_OF_CONDUCT.md` | ✅ Done |
| Create `SECURITY.md` | ✅ Done |
| Create `CHANGELOG.md` | ✅ Done |
| Create `.github/ISSUE_TEMPLATE/bug_report.md` | ✅ Done |
| Create `.github/ISSUE_TEMPLATE/feature_request.md` | ✅ Done |
| Create `.github/PULL_REQUEST_TEMPLATE.md` | ✅ Done |
| Create `.github/workflows/ci.yml` | ✅ Done |
| Extract `_parse_schemas()` helper function | ✅ Done |
| Extract `_parse_max_tokens()` helper function | ✅ Done |
| Extract `_extract_prompt_texts()` helper function | ✅ Done |
| Extract `_resolve_model_with_mod()` helper function | ✅ Done |
| Extract `_format_chat_completion_response()` helper function | ✅ Done |
| Extract `_format_streaming_chunk()` helper function | ✅ Done |
| **execute_impl.py Major Refactoring** | |
| Create `RequestState` dataclass for per-request state | ✅ Done |
| Create `BatchState` dataclass for batch-wide state | ✅ Done |
| Extract `_process_terminal_action()` helper | ✅ Done |
| Extract `_process_force_tokens_action()` helper | ✅ Done |
| Extract `_process_backtrack_action()` helper | ✅ Done |
| Extract `_initialize_batch_state()` helper | ✅ Done |
| Add section headers and phase documentation | ✅ Done |
| Remove remaining commented-out debug code | ✅ Done |
| Replace magic number with `_ERROR_TOKEN_MARKER` constant | ✅ Done |

---

## 13. In-Depth Code Review: Core Inference Path

This section provides a detailed review of the main inference entrypoint and execution loop, which are critical for code quality before open sourcing.

### Code Flow Overview

```
local.py (OpenAI-compatible server)
    └── QuotePipelineFactory.__call__() - Creates pipeline in worker
    └── create_app() - FastAPI app with /v1/chat/completions
        └── chat_completions() - Request handler
            └── pipeline.next_token() - Token generation
                └── execute_impl.py:execute() - Main generation loop
```

---

### 13.1 Review: `inference/src/quote/server/openai/local.py`

**File Size:** ~1150 lines (should consider splitting)

#### Issues Found

| Line(s) | Severity | Issue | Recommendation |
|---------|----------|-------|----------------|
| 519, 527, 620, 647-649, 755-756, 958, 970, 1095-1102 | 🔴 High | `print()` statements for debugging | Convert to `logging` module |
| 149-222 | 🟡 Medium | `_get_persistent_mod()` nested function is 73 lines | Extract to module-level function |
| 224-272 | 🟡 Medium | `_hot_execute()` nested function with complex error handling | Extract and add proper error types |
| 615-1109 | 🔴 High | `chat_completions()` is ~500 lines | Refactor into smaller functions |
| 743-753 | 🟡 Medium | Duplicated `user_api_key` extraction logic | Extract to helper function |
| 853-958 | 🟡 Medium | `gen()` async generator is deeply nested | Extract to top-level async function |
| 970 | 🟢 Low | `print("got error!!!!!!", tok.error)` | Remove or convert to logging |
| 989-1008 | 🟡 Medium | Tool call parsing with bare `except` | Add specific exception handling |

#### Specific Code Smells

**1. Duplicated User API Key Extraction (Lines 743-756)**
```python
user_api_key = request.headers.get("Authorization") or request.headers.get("x-api-key") or request.headers.get("x-user-api-key") or body.get("user_api_key")
if user_api_key.startswith("Bearer"):
    user_api_key = user_api_key.replace("Bearer ", "")
    print("user key:", user_api_key)
```
This pattern appears multiple times. Should be:
```python
def _extract_user_api_key(request: Request, body: dict) -> str | None:
    """Extract and normalize user API key from request headers or body."""
    ...
```

**2. Overly Long Function (chat_completions)**
The `chat_completions` function handles:
- Request parsing
- Message augmentation
- Tool normalization
- Streaming vs non-streaming
- Accumulator management
- Response formatting
- Debug logging

Each of these should be a separate function.

**3. Magic Strings**
```python
if text.startswith(f"<tool_call_{req_id}"):  # Line 994
```
Should be constants:
```python
TOOL_CALL_START_TAG = "<tool_call_{}"
TOOL_CALL_END_TAG = "</tool_call_{}"
```

**4. Bare Exception Handlers**
Multiple instances of:
```python
except Exception as e:
    print("error", e)
    pass
```
Should have specific exception types and proper logging.

#### Refactoring Recommendations

1. **Split into modules:**
   - `local.py` → Core server setup
   - `handlers.py` → Request handlers
   - `streaming.py` → SSE streaming logic
   - `helpers.py` → Utility functions

2. **Extract helper functions:**
   ```python
   def _extract_user_api_key(request, body) -> str | None
   def _parse_response_format(body) -> list[dict]
   def _build_sampling_params(body) -> SamplingParams
   def _format_chat_response(req_id, model, text, ...) -> dict
   def _format_streaming_chunk(req_id, model, token, ...) -> dict
   ```

3. **Add type hints to all functions**

4. **Replace print statements:**
   ```python
   import logging
   logger = logging.getLogger(__name__)
   
   # Instead of: print("error", e)
   logger.error("Failed to parse response format: %s", e)
   ```

---

### 13.2 Review: `inference/src/quote/hot/execute_impl.py`

**File Size:** ~1690 lines (very large, needs refactoring)

#### Architecture Overview

The `execute()` function is the heart of the inference loop:
1. **Prefill Phase** - Process initial prompt, allow mods to adjust
2. **Generation Loop** - For each step:
   - Forward pass (compute logits)
   - Mod dispatch (ForwardPass event)
   - Sample token
   - Mod dispatch (Sampled event)
   - Add token to output
   - Mod dispatch (Added event)
   - Handle backtracking
   - Update KV cache
3. **Finalization** - Build output per request

#### Issues Found

| Line(s) | Severity | Issue | Recommendation |
|---------|----------|-------|----------------|
| 354-1605 | 🔴 Critical | `execute()` is 1250+ lines | Must be refactored |
| 339-340 | 🟡 Medium | `print(f"[mods] ToolCalls encode failed: {e}")` | Use logging |
| 502-505 | 🟡 Medium | `print(f"[mods][AdjustedPrefill] Failed...")` | Use logging |
| 686 | 🟡 Medium | `print("ERROR: ", e)` | Use logging |
| 714-717 | 🔴 High | `print("WARNING: Invalid type in action logits")` | Use logging.warning() |
| 1488-1507 | 🟢 Low | Commented-out debug prints | Remove dead code |
| 1509 | 🟡 Medium | `mod_manager.delayed_backtrack` - bare attribute access | Check if intentional or bug |
| 1575 | 🟡 Medium | `print("error stepping...")` | Use logging |
| 600-602 | 🟢 Low | Comment "Refactor: extract repeated..." | Address the TODO |

#### Structural Issues

**1. Main Loop Too Complex (Lines 601-1485)**
The main generation loop has:
- 6 levels of nesting in places
- Multiple inline event dispatching blocks
- Duplicated action handling patterns
- Complex backtracking logic interleaved with main flow

**2. Duplicated Action Handling**
The same pattern appears 3 times (ForwardPass, Sampled, Added events):
```python
for action in mod_manager.dispatch(ev_...):
    _log_mod_action(...)
    if isinstance(action, ForceTokens):
        # ... same logic
    elif isinstance(action, Backtrack):
        # ... same logic
    elif isinstance(action, (ForceOutput, ToolCalls, EmitError)):
        # ... same logic
```

Should be extracted to:
```python
def _handle_mod_action(action, rid, mod_manager, ...) -> bool:
    """Handle a mod action, return True if should break."""
    ...
```

**3. Magic Numbers and Constants**
```python
_MAX_TOOL_PAYLOAD_CHARS = 2048  # Good - defined as constant
_MAX_ACTION_TOKEN_PREVIEW = 128  # Good - defined as constant
# But also:
999_999_999_999  # Line 1569 - magic number for error token
```

**4. Complex State Management**
Multiple dictionaries track per-request state:
```python
terminal_force_outputs: Dict[str, list[int]] = {}
terminal_tool_calls: Dict[str, Any] = {}
terminal_errors: Dict[str, str] = {}
done_requests: set[str] = set()
req_accumulators: Dict[str, IngestAccumulator] = {}
placeholder_positions: Dict[str, int | None] = {}
skip_step_progress: Dict[str, bool] = {}
skip_step_token: Dict[str, int | None] = {}
rewind_cache_n = {}
```

Should be consolidated into a `RequestState` dataclass:
```python
@dataclass
class RequestExecutionState:
    request_id: str
    accumulator: IngestAccumulator | None = None
    terminal_output: list[int] | None = None
    terminal_tool_call: Any = None
    terminal_error: str | None = None
    is_done: bool = False
    placeholder_position: int | None = None
    skip_progress: bool = False
    skip_token: int | None = None
    rewind_n: int | None = None
```

#### Refactoring Recommendations

**Phase 1: Extract Helper Functions**
```python
# Event handling
def _dispatch_prefilled_event(mod_manager, context, ...) -> list[Action]
def _dispatch_forward_pass_event(mod_manager, logits, ...) -> list[Action]
def _dispatch_sampled_event(mod_manager, token, ...) -> list[Action]
def _dispatch_added_event(mod_manager, tokens, forced, ...) -> list[Action]

# Action processing
def _process_force_tokens(action, mod_manager, rid) -> None
def _process_backtrack(action, mod_manager, context, rid) -> int | None
def _process_terminal(action, state) -> None

# State updates
def _update_generated_tokens(generated, new_tokens, placeholders, ...) -> Tensor
def _update_kv_cache(curr_step_inputs, rewind_n, ...) -> None
def _update_step_inputs(curr_step_inputs, tokens, offsets, ...) -> None
```

**Phase 2: Consolidate State**
```python
@dataclass
class BatchExecutionState:
    """Tracks execution state for all requests in a batch."""
    request_states: dict[str, RequestExecutionState]
    mod_manager: ModManager
    generated_tokens: Tensor
    placeholder_token_id: int
    
    def mark_done(self, rid: str) -> None: ...
    def is_all_done(self) -> bool: ...
    def get_pending_forced(self, rid: str) -> list[int]: ...
```

**Phase 3: Split the Loop**
```python
def execute(pipeline, inputs):
    state = _initialize_batch_state(pipeline, inputs)
    _handle_prefill_phase(state, pipeline, inputs)
    
    for step in range(num_steps):
        if state.is_all_done():
            break
        _execute_generation_step(state, pipeline, step)
    
    return _finalize_outputs(state, pipeline)

def _execute_generation_step(state, pipeline, step):
    logits = _forward_pass(state, pipeline)
    logits = _handle_forward_pass_mods(state, logits)
    tokens = _sample_tokens(state, pipeline, logits)
    _handle_sampled_mods(state, tokens)
    _handle_added_mods(state, tokens)
    _update_state_for_next_step(state, pipeline, tokens)
```

#### Dead Code to Remove

| Lines | Code |
|-------|------|
| 1488-1507 | Commented-out debug prints |
| 438-442 (backup files) | Old passthrough code comments |

#### Comments to Address

```python
# Line 600-602:
# Refactor: extract repeated ModManager handling into helpers; prefer structured logging.
# Refactor: centralize terminal actions and placeholder/backtrack behavior.
```

These TODOs should either be addressed or converted to GitHub issues.

---

### 13.3 Recommended Cleanup Order

**Immediate (Before Open Source):**
1. ~~Replace all `print()` with `logging` calls~~ ✅ DONE
2. ~~Remove commented-out debug code~~ ✅ DONE
3. Add missing type hints to public functions
4. ~~Extract the duplicated user API key logic~~ ✅ DONE

**Short-term (First Release):**
1. ~~Extract `chat_completions()` into smaller functions~~ ✅ DONE (partially - helpers extracted)
2. ~~Create `RequestExecutionState` dataclass~~ ✅ DONE (as `RequestState` and `BatchState`)
3. ~~Extract duplicated mod action handling~~ ✅ DONE (`_process_terminal_action`, `_process_force_tokens_action`, `_process_backtrack_action`)
4. Add docstrings to all public functions

**Medium-term (Post-Release):**
1. Split `local.py` into multiple modules
2. Refactor `execute()` into phases
3. Add comprehensive logging throughout
4. Add metrics/instrumentation hooks

---

## Notes

- The codebase is generally well-structured with good separation of concerns
- The SDK has good documentation in `sdk/README.md`
- The examples in `examples/` are valuable for users but need cleanup
- Consider whether `inference/README.md` should be simplified for external users
- The mod unit test framework is comprehensive and well-documented
- ~~**Critical**: `execute_impl.py` is the highest priority for cleanup due to its complexity and central role~~ ✅ Major refactoring complete
- ~~**Critical**: `local.py` needs print statement cleanup before any public visibility~~ ✅ Cleaned up
- `execute_impl.py` now has clear section organization with `RequestState`/`BatchState` dataclasses for state management
- The main `execute()` function is still long (~1100 lines) but now has clear phase documentation and extracted helpers