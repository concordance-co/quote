"""Pytest fixtures and utilities for mod unit tests.

This module provides fixtures to load and test mods in an isolated environment
without requiring a running server.
"""

import sys
import types
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Iterable
from dataclasses import dataclass, field
from types import SimpleNamespace
import importlib.util
import inspect

import pytest

# Add inference src, SDK, and shared to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INFERENCE_SRC = PROJECT_ROOT / "inference" / "src"
SDK_PATH = PROJECT_ROOT / "sdk"
SHARED_SRC = PROJECT_ROOT / "shared" / "src"
if str(INFERENCE_SRC) not in sys.path:
    sys.path.insert(0, str(INFERENCE_SRC))
if str(SDK_PATH) not in sys.path:
    sys.path.insert(0, str(SDK_PATH))
if str(SHARED_SRC) not in sys.path:
    sys.path.insert(0, str(SHARED_SRC))


class ContextInfo:
    tokens: Any
    _prompt_len: Any
    logprobs: Any
    max_tokens: Any

def _install_dotenv_stub() -> None:
    """Install stub for dotenv module."""
    if "dotenv" in sys.modules:
        return
    dotenv = types.ModuleType("dotenv")

    def load_dotenv(*_args: Any, **_kwargs: Any) -> None:
        return None

    dotenv.load_dotenv = load_dotenv  # type: ignore[attr-defined]
    sys.modules["dotenv"] = dotenv


def _install_max_stubs() -> None:
    """Install stubs for max modules to avoid heavy dependencies."""
    # Overwrite any real max modules so tests avoid heavy dependencies.
    for name in list(sys.modules):
        if name == "max" or name.startswith("max."):
            sys.modules.pop(name, None)

    max_pkg = types.ModuleType("max")
    sys.modules["max"] = max_pkg

    driver = types.ModuleType("max.driver")

    class Tensor:
        def __init__(self, value: Any | None = None) -> None:
            self.value = value

        def to(self, _device: Any) -> "Tensor":
            return self

        @classmethod
        def from_numpy(cls, array: Any) -> "Tensor":
            return cls(array)

        def to_numpy(self) -> Any:
            """Convert tensor to numpy array."""
            if hasattr(self.value, 'to_numpy'):
                return self.value.to_numpy()
            return self.value

    driver.Tensor = Tensor  # type: ignore[attr-defined]
    sys.modules["max.driver"] = driver
    max_pkg.driver = driver  # type: ignore[attr-defined]

    dtype = types.ModuleType("max.dtype")

    class DType:
        pass

    dtype.DType = DType  # type: ignore[attr-defined]
    sys.modules["max.dtype"] = dtype
    max_pkg.dtype = dtype  # type: ignore[attr-defined]


# Install stubs before importing shared modules
_install_dotenv_stub()
_install_max_stubs()


from shared.types import (
    Added,
    AdjustedLogits,
    AdjustedPrefill,
    Backtrack,
    ForceOutput,
    ForceTokens,
    ModAction,
    ModEvent,
    Noop,
    Prefilled,
    Sampled,
    ForwardPass,
    ToolCalls,
)
from max.driver import Tensor
from quote.mods.manager import ModManager


class SimpleTokenizer:
    """Simple tokenizer for testing that uses character-level encoding."""

    def __init__(self):
        self.eos_token_id = 0
        self.bos_token_id = 1

    def encode(self, text: str, add_special_tokens: bool = True) -> List[int]:
        """Encode text as list of character codes (offset to avoid special tokens)."""
        tokens = [ord(c) + 10 for c in text]
        if add_special_tokens:
            tokens = [self.bos_token_id] + tokens
        return tokens

    def decode(self, tokens: List[int], skip_special_tokens: bool = True) -> str:
        """Decode tokens back to text."""
        filtered_tokens = []
        for t in tokens:
            if skip_special_tokens and t in (self.eos_token_id, self.bos_token_id):
                continue
            if t >= 10:
                filtered_tokens.append(t - 10)

        try:
            return ''.join(chr(t) for t in filtered_tokens)
        except (ValueError, OverflowError):
            return ""


@dataclass
class ModTestContext:
    """Context for running a single mod test."""
    mod_function: Callable
    mod_name: str
    event_type: str
    tokenizer: SimpleTokenizer = field(default_factory=SimpleTokenizer)
    mod_manager: Optional[ModManager] = None
    request_id: str = "test_request"

    def __post_init__(self):
        if self.mod_manager is None:
            self.mod_manager = ModManager([self.mod_function], tokenizer=self.tokenizer)


def load_mod_from_file(filepath: Path) -> Tuple[Callable, str]:
    """Load a mod function from a Python file.

    Args:
        filepath: Path to the Python file containing the mod

    Returns:
        Tuple of (mod_function, mod_name)
    """
    # Load the module with unique name to avoid import conflicts
    # Include parent directory in module name (e.g., "prefilled_test_noop")
    module_name = f"{filepath.parent.name}_{filepath.stem}"
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load module from {filepath}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    # Find the @mod decorated function
    mod_function = None
    for name, obj in inspect.getmembers(module):
        if inspect.isfunction(obj) and hasattr(obj, '__wrapped__'):
            # This is likely a decorated function
            mod_function = obj
            break
        elif inspect.isfunction(obj) and name.startswith('test_'):
            # Fallback: find functions starting with test_
            mod_function = obj
            break

    if mod_function is None:
        raise ValueError(f"Could not find mod function in {filepath}")

    mod_name = mod_function.__name__
    return mod_function, mod_name


def discover_test_mods() -> List[Tuple[str, Path]]:
    """Discover all test mod files.

    Returns:
        List of tuples: (event_type, test_file_path)
    """
    test_root = Path(__file__).parent
    test_mods = []

    for event_dir in test_root.iterdir():
        if event_dir.is_dir() and not event_dir.name.startswith('__'):
            event_name = event_dir.name
            for test_file in event_dir.glob("test_*.py"):
                test_mods.append((event_name, test_file))

    return sorted(test_mods)


@pytest.fixture
def tokenizer():
    """Provide a simple tokenizer for tests."""
    return SimpleTokenizer()


@pytest.fixture
def mod_context(tokenizer):
    """Factory fixture to create ModTestContext instances."""
    def _create_context(mod_file: Path) -> ModTestContext:
        mod_function, mod_name = load_mod_from_file(mod_file)
        event_type = mod_file.parent.name
        return ModTestContext(
            mod_function=mod_function,
            mod_name=mod_name,
            event_type=event_type,
            tokenizer=tokenizer
        )
    return _create_context


def create_prefilled_event(
    request_id: str,
    prompt: str,
    tokenizer: SimpleTokenizer,
    step: int = 0,
    max_steps: int = 50
) -> Prefilled:
    """Create a Prefilled event for testing."""
    prompt_tokens = tokenizer.encode(prompt, add_special_tokens=True)

    # Create context_info as an object with attributes
    from types import SimpleNamespace
    context_info = SimpleNamespace(
        tokens=prompt_tokens,
        _prompt_len=len(prompt_tokens),
        logprobs=[],
        max_tokens=max_steps,
    )

    return Prefilled(
        request_id=request_id,
        step=step,
        max_steps=max_steps,
        context_info=context_info,
    )


def create_forward_pass_event(
    request_id: str,
    tokens: List[int],
    logits: Optional[Tensor] = None,
    step: int = 0
) -> ForwardPass:
    """Create a ForwardPass event for testing."""
    if logits is None:
        # Create dummy logits as Tensor
        # Large vocab size to accommodate all character codes (including Unicode)
        vocab_size = 50000
        import numpy as np
        logits_array = np.zeros((1, vocab_size), dtype=np.float32)
        logits = Tensor.from_numpy(logits_array)

    return ForwardPass(
        request_id=request_id,
        step=step,
        logits=logits,
    )


def create_added_event(
    request_id: str,
    added_tokens: List[int],
    forced: bool = False,
    step: int = 0,
) -> Added:
    """Create an Added event for testing."""
    return Added(
        request_id=request_id,
        step=step,
        added_tokens=added_tokens,
        forced=forced,
    )


def create_sampled_event(
    request_id: str,
    token: int,
    step: int = 0,
) -> Sampled:
    """Create a Sampled event for testing."""
    return Sampled(
        request_id=request_id,
        step=step,
        sampled_token=token,
    )


# Test configuration helpers
class TestValidator:
    """Validators for different test types."""

    @staticmethod
    def validate_noop(action: ModAction) -> Tuple[bool, str]:
        """Validate noop action."""
        if isinstance(action, Noop):
            return True, "Noop action returned"
        return False, f"Expected Noop, got {type(action).__name__}"

    @staticmethod
    def validate_adjust_prefill(action: ModAction, expected_text: str = "goodbye") -> Tuple[bool, str]:
        """Validate adjust_prefill action."""
        if isinstance(action, AdjustedPrefill):
            # Would need tokenizer to decode, but we can check it exists
            return True, f"AdjustedPrefill action with {len(action.tokens)} tokens"
        return False, f"Expected AdjustedPrefill, got {type(action).__name__}"

    @staticmethod
    def validate_force_output(action: ModAction) -> Tuple[bool, str]:
        """Validate force_output action."""
        if isinstance(action, ForceOutput):
            return True, f"ForceOutput action with text: {action.text[:50]}"
        return False, f"Expected ForceOutput, got {type(action).__name__}"

    @staticmethod
    def validate_tool_calls(action: ModAction) -> Tuple[bool, str]:
        """Validate tool_calls action."""
        if isinstance(action, ToolCalls):
            return True, f"ToolCalls action with {len(action.tools)} tools"
        return False, f"Expected ToolCalls, got {type(action).__name__}"

    @staticmethod
    def validate_force_tokens(action: ModAction) -> Tuple[bool, str]:
        """Validate force_tokens action."""
        if isinstance(action, ForceTokens):
            return True, f"ForceTokens action with {len(action.tokens)} tokens"
        return False, f"Expected ForceTokens, got {type(action).__name__}"

    @staticmethod
    def validate_backtrack(action: ModAction) -> Tuple[bool, str]:
        """Validate backtrack action."""
        if isinstance(action, Backtrack):
            return True, f"Backtrack action by {action.num_tokens} tokens"
        return False, f"Expected Backtrack, got {type(action).__name__}"

    @staticmethod
    def validate_adjust_logits(action: ModAction) -> Tuple[bool, str]:
        """Validate adjust_logits action."""
        if isinstance(action, AdjustedLogits):
            return True, f"AdjustedLogits action"
        return False, f"Expected AdjustedLogits, got {type(action).__name__}"


@pytest.fixture
def validator():
    """Provide test validators."""
    return TestValidator()


# Parametrization data
def pytest_generate_tests(metafunc):
    """Automatically parametrize tests based on discovered mod files."""
    if "mod_file" in metafunc.fixturenames:
        test_mods = discover_test_mods()
        # Create test IDs like "prefilled/test_noop"
        ids = [f"{event_type}/{test_file.stem}" for event_type, test_file in test_mods]
        metafunc.parametrize("mod_file", [test_file for _, test_file in test_mods], ids=ids)
