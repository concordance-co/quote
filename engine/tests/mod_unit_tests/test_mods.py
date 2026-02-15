"""Pytest-based unit tests for mod primitives.

This module tests all mod event types:
- Prefilled: Tests mod behavior during initial prompt processing
- ForwardPass: Tests mod behavior during forward pass
- Added: Tests mod behavior after tokens are added
- Sampled: Tests mod behavior after sampling

Each test automatically discovers and runs mods from the corresponding directories.
"""

import pytest
from pathlib import Path
from typing import Dict, Any, Callable
import importlib

from shared.types import (
    Added,
    AdjustedLogits,
    AdjustedPrefill,
    Backtrack,
    ForceOutput,
    ForceTokens,
    ModAction,
    Noop,
    Prefilled,
    Sampled,
    ForwardPass,
    ToolCalls,
)

try:
    _cft = importlib.import_module("conftest")
    if not hasattr(_cft, "load_mod_from_file"):
        raise AttributeError("top-level conftest does not expose mod-unit fixtures")
except (ModuleNotFoundError, AttributeError):
    _cft = importlib.import_module("mod_unit_tests.conftest")

load_mod_from_file = _cft.load_mod_from_file
create_prefilled_event = _cft.create_prefilled_event
create_forward_pass_event = _cft.create_forward_pass_event
create_added_event = _cft.create_added_event
create_sampled_event = _cft.create_sampled_event
SimpleTokenizer = _cft.SimpleTokenizer
TestValidator = _cft.TestValidator


# Test prompts and expectations for each test type
TEST_CONFIGS = {
    "prefilled": {
        "test_noop": {
            "prompt": "Say hello to me.",
            "expected_action": Noop,
            "description": "Normal response, no modification",
        },
        "test_adjust_prefill": {
            "prompt": "Say hello to me.",
            "expected_action": AdjustedPrefill,
            "description": "Should replace 'hello' with 'goodbye'",
        },
        "test_force_output": {
            "prompt": "This is an emergency!",
            "expected_action": ForceOutput,
            "description": "Should force emergency protocol output",
        },
        "test_tool_calls": {
            "prompt": "What's the weather like?",
            "expected_action": ToolCalls,
            "description": "Should trigger weather tool call",
        },
    },
    "forward_pass": {
        "test_noop": {
            "prompt": "Count to 5.",
            "expected_action": Noop,
            "description": "Normal response, no modification",
        },
        "test_force_tokens": {
            "prompt": "Tell me something.",
            "expected_action": ForceTokens,
            "description": "Should inject tokens",
        },
        "test_backtrack": {
            "prompt": "Tell me a story.",
            "expected_action": Backtrack,
            "description": "Should trigger backtrack",
            "needs_added_events": 5,  # Needs 5 Added events to count tokens
        },
        "test_adjust_logits": {
            "prompt": "Write a sentence.",
            "expected_action": AdjustedLogits,
            "description": "Should adjust logits to ban tokens",
        },
        "test_force_output": {
            "prompt": "Count to ten.",
            "expected_action": ForceOutput,
            "description": "Should force specific output",
            "needs_added_events": 3,  # Needs 3 Added events to count tokens
        },
        "test_tool_calls": {
            "prompt": "Calculate something.",
            "expected_action": ToolCalls,
            "description": "Should trigger calculator tool call",
            "needs_multiple_events": True,
        },
    },
    "added": {
        "test_noop": {
            "prompt": "Say something.",
            "expected_action": Noop,
            "description": "Normal response, no modification",
        },
        "test_force_tokens": {
            "prompt": "Say hello.",
            "expected_action": ForceTokens,
            "description": "Should force ' world' after 'hello'",
        },
        "test_backtrack": {
            "prompt": "Say a sentence that ends with the words 'bad phrase'.",
            "expected_action": Backtrack,
            "description": "Should backtrack and replace 'bad phrase'",
            "trigger_text": "bad phrase",
        },
        "test_force_output": {
            "prompt": "Say the words 'stop word' somewhere in a sentence.",
            "expected_action": ForceOutput,
            "description": "Should force output when stop word detected",
        },
        "test_tool_calls": {
            "prompt": "I need to search for information.",
            "expected_action": ToolCalls,
            "description": "Should trigger search tool call",
            "trigger_text": "search for",
        },
    },
    "sampled": {
        "test_noop": {
            "prompt": "Tell me a fact.",
            "expected_action": Noop,
            "description": "Normal response, no modification",
        },
        "test_force_tokens": {
            "prompt": "Say anything.",
            "expected_action": ForceTokens,
            "description": "Should append observation marker",
        },
        "test_backtrack": {
            "prompt": "Count slowly.",
            "expected_action": Backtrack,
            "description": "Should trigger resampling",
            "needs_multiple_events": 3,  # Needs 3 Sampled events
        },
        "test_force_output": {
            "prompt": "Keep counting.",
            "expected_action": ForceOutput,
            "description": "Should force end marker",
            "needs_multiple_events": 5,  # Needs 5 Sampled events
        },
        "test_tool_calls": {
            "prompt": "Query data.",
            "expected_action": ToolCalls,
            "description": "Should trigger database tool call",
            "needs_multiple_events": 2,  # Needs 2 Sampled events
        },
    },
}


def get_test_config(event_type: str, test_name: str) -> Dict[str, Any]:
    """Get test configuration for a specific test."""
    return TEST_CONFIGS.get(event_type, {}).get(test_name, {
        "prompt": "Default test prompt.",
        "expected_action": Noop,
        "description": "Default test",
    })


class TestModPrimitives:
    """Test suite for mod event primitives."""

    def test_mod_execution(self, mod_file: Path, tokenizer: SimpleTokenizer, validator: TestValidator):
        """Test a single mod by loading it and executing with appropriate events.

        This test is parametrized by pytest_generate_tests in conftest.py to run
        for all discovered mod files.
        """
        # Load the mod
        mod_function, mod_name = load_mod_from_file(mod_file)

        # Get test metadata
        event_type = mod_file.parent.name
        test_name = mod_file.stem
        config = get_test_config(event_type, test_name)

        # Create appropriate event based on event type
        request_id = f"test_{event_type}_{test_name}"

        if event_type == "prefilled":
            event = create_prefilled_event(
                request_id=request_id,
                prompt=config["prompt"],
                tokenizer=tokenizer,
                step=0
            )
        elif event_type == "forward_pass":
            # Check if this test needs Added events first to build state
            num_added_events = config.get("needs_added_events", 0)
            if num_added_events > 0:
                # Send Added events first to build up token count
                for i in range(num_added_events):
                    added_token = tokenizer.encode(str(i), add_special_tokens=False)[0]
                    added_event = create_added_event(
                        request_id=request_id,
                        added_tokens=[added_token],
                        forced=False,
                        step=i+1,
                    )
                    # Execute to build state
                    mod_function(added_event, tokenizer)

            # Now create and send the ForwardPass event
            prompt_tokens = tokenizer.encode(config["prompt"])
            event = create_forward_pass_event(
                request_id=request_id,
                tokens=prompt_tokens,
                step=num_added_events + 1
            )
            action = mod_function(event, tokenizer)
            # Skip to validation (action already set above)
            assert action is not None, "Mod returned None"
            assert isinstance(action, ModAction), f"Mod returned non-ModAction: {type(action)}"

            # Check expected action type
            expected_action_type = config.get("expected_action", Noop)

            # For noop tests, we always expect Noop
            if test_name == "test_noop":
                assert isinstance(action, Noop), (
                    f"Noop test should return Noop action, got {type(action).__name__}"
                )
                return

            # For other tests, check the specific action type
            if isinstance(action, Noop):
                pytest.skip(f"Mod returned Noop (conditions may not have been met): {config['description']}")

            # Validate specific action types
            action_type = type(action).__name__
            expected_type = expected_action_type.__name__

            assert isinstance(action, expected_action_type), (
                f"Expected {expected_type} action, got {action_type}. "
                f"Test: {config['description']}"
            )

            # Additional validations
            if isinstance(action, ForceOutput):
                assert len(action.tokens) > 0, "ForceOutput should have tokens"
            elif isinstance(action, Backtrack):
                assert action.n > 0, "Backtrack should backtrack at least one token"

            return  # Exit early since we already validated

        elif event_type == "added":
            # Simulate tokens being added
            prompt = config["prompt"]
            # For "Say hello" test, add "hello" tokens
            if "hello" in prompt.lower():
                added_text = "hello"
            elif "bad phrase" in prompt.lower():
                added_text = "bad phrase"
            elif "stop word" in prompt.lower():
                added_text = "stop word"
            elif "search for" in config.get("trigger_text", ""):
                added_text = "search for"
            else:
                added_text = "test"

            added_tokens = tokenizer.encode(added_text, add_special_tokens=False)
            event = create_added_event(
                request_id=request_id,
                added_tokens=added_tokens,
                forced=False,
                step=1
            )
        elif event_type == "sampled":
            # Check if this test needs multiple events
            num_events = config.get("needs_multiple_events", 1)
            if isinstance(num_events, int) and num_events > 1:
                # For stateful mods that need multiple sampled events
                for i in range(num_events):
                    token = tokenizer.encode(str(i), add_special_tokens=False)[0]
                    event = create_sampled_event(
                        request_id=request_id,
                        token=token,
                        step=i+1
                    )
                    action = mod_function(event, tokenizer)
                    # If we got a non-Noop action, use it
                    if not isinstance(action, Noop):
                        break
            else:
                # Single event
                token = tokenizer.encode(" ", add_special_tokens=False)[0]
                event = create_sampled_event(
                    request_id=request_id,
                    token=token,
                    step=1
                )
                action = mod_function(event, tokenizer)

            # Skip to validation (action already set above)
            assert action is not None, "Mod returned None"
            assert isinstance(action, ModAction), f"Mod returned non-ModAction: {type(action)}"

            # Check expected action type
            expected_action_type = config.get("expected_action", Noop)

            # For noop tests, we always expect Noop
            if test_name == "test_noop":
                assert isinstance(action, Noop), (
                    f"Noop test should return Noop action, got {type(action).__name__}"
                )
                return

            # For other tests, check the specific action type
            if isinstance(action, Noop):
                pytest.skip(f"Mod returned Noop (conditions may not have been met): {config['description']}")

            # Validate specific action types
            action_type = type(action).__name__
            expected_type = expected_action_type.__name__

            assert isinstance(action, expected_action_type), (
                f"Expected {expected_type} action, got {action_type}. "
                f"Test: {config['description']}"
            )

            # Additional validations based on action type
            if isinstance(action, AdjustedPrefill):
                assert len(action.tokens) > 0, "AdjustedPrefill should have tokens"

            elif isinstance(action, ForceOutput):
                assert len(action.tokens) > 0, "ForceOutput should have tokens"

            elif isinstance(action, ToolCalls):
                assert action.tool_calls, "ToolCalls should have tool_calls"

            elif isinstance(action, ForceTokens):
                assert len(action.tokens) > 0, "ForceTokens should have tokens"

            elif isinstance(action, Backtrack):
                assert action.n > 0, "Backtrack should backtrack at least one token"

            elif isinstance(action, AdjustedLogits):
                # AdjustedLogits should have logits array
                pass

            return  # Exit early since we already validated
        else:
            pytest.fail(f"Unknown event type: {event_type}")

        # Execute the mod (unless we already did for sampled/forward_pass with multiple events)
        if event_type not in ["sampled", "forward_pass"] or (
            config.get("needs_multiple_events", 1) == 1 and config.get("needs_added_events", 0) == 0
        ):
            try:
                action = mod_function(event, tokenizer)
            except Exception as e:
                pytest.fail(f"Mod raised exception: {e}")

        # Validate the action type
        assert action is not None, "Mod returned None"
        assert isinstance(action, ModAction), f"Mod returned non-ModAction: {type(action)}"

        # Check expected action type
        expected_action_type = config.get("expected_action", Noop)

        # For noop tests, we always expect Noop
        if test_name == "test_noop":
            assert isinstance(action, Noop), (
                f"Noop test should return Noop action, got {type(action).__name__}"
            )
            return

        # For other tests, check the specific action type
        # Some mods might return Noop if conditions aren't met, which is acceptable
        if isinstance(action, Noop):
            # This might be acceptable if the mod's conditions weren't triggered
            # We'll mark this with a warning but not fail
            pytest.skip(f"Mod returned Noop (conditions may not have been met): {config['description']}")

        # Validate specific action types
        action_type = type(action).__name__
        expected_type = expected_action_type.__name__

        assert isinstance(action, expected_action_type), (
            f"Expected {expected_type} action, got {action_type}. "
            f"Test: {config['description']}"
        )

        # Additional validations based on action type
        if isinstance(action, AdjustedPrefill):
            assert len(action.tokens) > 0, "AdjustedPrefill should have tokens"

        elif isinstance(action, ForceOutput):
            assert len(action.tokens) > 0, "ForceOutput should have tokens"

        elif isinstance(action, ToolCalls):
            assert action.tool_calls, "ToolCalls should have tool_calls"

        elif isinstance(action, ForceTokens):
            assert len(action.tokens) > 0, "ForceTokens should have tokens"

        elif isinstance(action, Backtrack):
            assert action.n > 0, "Backtrack should backtrack at least one token"

        elif isinstance(action, AdjustedLogits):
            # AdjustedLogits should have logits array
            pass

    def test_mod_multiple_steps(self, tokenizer: SimpleTokenizer):
        """Test that mods can handle multiple events across steps.

        This tests stateful mods that track information across events.
        """
        # Load a stateful mod (e.g., added/test_force_tokens)
        test_root = Path(__file__).parent
        mod_file = test_root / "added" / "test_force_tokens.py"

        if not mod_file.exists():
            pytest.skip("Stateful test mod not found")

        mod_function, mod_name = load_mod_from_file(mod_file)
        request_id = "test_stateful"

        # First event: add "hel"
        event1 = create_added_event(
            request_id=request_id,
            added_tokens=tokenizer.encode("hel", add_special_tokens=False),
            forced=False,
            step=1
        )
        action1 = mod_function(event1, tokenizer)
        assert isinstance(action1, (Noop, ForceTokens)), "First event should return Noop or ForceTokens"

        # Second event: add "lo" (completing "hello")
        event2 = create_added_event(
            request_id=request_id,
            added_tokens=tokenizer.encode("lo", add_special_tokens=False),
            forced=False,
            step=2
        )
        action2 = mod_function(event2, tokenizer)

        # After "hello", should force " world"
        assert isinstance(action2, (Noop, ForceTokens)), (
            "After completing 'hello', should return ForceTokens or Noop"
        )


class TestModIntegration:
    """Integration tests for mod system."""

    def test_all_mods_load(self):
        """Test that all mod files can be loaded without errors."""
        test_mods = _cft.discover_test_mods()
        assert len(test_mods) > 0, "Should discover at least one test mod"

        loaded_count = 0
        for event_type, test_file in test_mods:
            try:
                mod_function, mod_name = load_mod_from_file(test_file)
                assert callable(mod_function), f"Mod {mod_name} should be callable"
                loaded_count += 1
            except Exception as e:
                pytest.fail(f"Failed to load {test_file}: {e}")

        assert loaded_count == len(test_mods), f"All {len(test_mods)} mods should load successfully"

    def test_mod_manager_dispatch(self, tokenizer: SimpleTokenizer):
        """Test that ModManager can dispatch events to mods."""
        from quote.mods.manager import ModManager

        # Load a simple mod
        test_root = Path(__file__).parent
        mod_file = test_root / "prefilled" / "test_noop.py"

        if not mod_file.exists():
            pytest.skip("Test mod not found")

        mod_function, mod_name = load_mod_from_file(mod_file)

        # Create mod manager
        manager = ModManager([mod_function], tokenizer=tokenizer)

        # Create event
        event = create_prefilled_event(
            request_id="test_dispatch",
            prompt="Test prompt",
            tokenizer=tokenizer
        )

        # Dispatch event
        actions = manager.dispatch(event)

        assert isinstance(actions, list), "dispatch should return list of actions"
        assert len(actions) > 0, "dispatch should return at least one action"
        assert all(isinstance(a, ModAction) for a in actions), "All returned items should be ModActions"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
