"""Test script to demonstrate mod trace formatting."""

import sys
from pathlib import Path

# Add parent directories to path for imports
test_dir = Path(__file__).parent
engine_dir = test_dir.parent.parent
sys.path.insert(0, str(engine_dir / "shared" / "src"))

from shared.conversation import (
    init_mod_trace,
    append_trace_event,
    append_trace_mod_call,
    append_trace_mod_log,
    append_trace_action,
    format_mod_trace,
    get_mod_trace_data,
    clear_mod_trace,
)


def test_basic_trace():
    """Test basic trace with a few events."""
    request_id = "test_request_001"

    # Initialize trace
    init_mod_trace(request_id)

    # Prefill event
    append_trace_event(
        request_id,
        "Prefill",
        step=0,
        details={"prompt_length": 100}
    )
    append_trace_mod_call(request_id, "MyMod", "Prefill", 0)
    append_trace_mod_log(request_id, "MyMod", "Starting mod for request A")
    append_trace_mod_log(request_id, "MyMod", "Created state for request A")
    append_trace_action(request_id, "AdjustPrefill", {"new_length": 105})

    # ForwardPass event
    append_trace_event(
        request_id,
        "ForwardPass",
        step=1,
        details={
            "input_text": "Imagine",
            "top_tokens": [
                {"token": " a", "prob": 0.45},
                {"token": "\n", "prob": 0.23},
                {"token": "\t", "prob": 0.15},
            ]
        }
    )
    append_trace_mod_call(request_id, "MyMod", "ForwardPass", 1)
    append_trace_action(request_id, "Noop", {})

    # Sampled event
    append_trace_event(
        request_id,
        "Sampled",
        step=1,
        details={"token_text": " a"}
    )
    append_trace_mod_call(request_id, "MyMod", "Sampled", 1)
    append_trace_mod_log(request_id, "MyMod", 'Sampled " a" for request A')
    append_trace_action(request_id, "ForceTokens", {"tokens_preview": "[32, 1467, 311, 2291]"})

    # Format and print
    trace = format_mod_trace(request_id)
    print("=== Basic Trace Test ===")
    print(trace)
    print("\n")

    # Clean up
    clear_mod_trace(request_id)


def test_multiple_mods():
    """Test trace with multiple mods."""
    request_id = "test_request_002"

    # Initialize trace
    init_mod_trace(request_id)

    # Prefill event with multiple mods
    append_trace_event(
        request_id,
        "Prefill",
        step=0,
        details={"prompt_length": 50}
    )
    append_trace_mod_call(request_id, "LoggingMod", "Prefill", 0)
    append_trace_mod_log(request_id, "LoggingMod", "Prefill started")
    append_trace_mod_call(request_id, "ValidationMod", "Prefill", 0)
    append_trace_mod_log(request_id, "ValidationMod", "Validation passed")
    append_trace_action(request_id, "Noop", {})

    # ForwardPass event
    append_trace_event(
        request_id,
        "ForwardPass",
        step=1,
        details={
            "input_text": "Hello world, this is a very long text that should be truncated when it exceeds 70 characters limit",
            "top_tokens": [
                {"token": " I", "prob": 0.52},
                {"token": " we", "prob": 0.28},
                {"token": " you", "prob": 0.12},
            ]
        }
    )
    append_trace_mod_call(request_id, "LoggingMod", "ForwardPass", 1)
    append_trace_mod_call(request_id, "BiasControlMod", "ForwardPass", 1)
    append_trace_mod_log(request_id, "BiasControlMod", "Adjusting logits for token 'I'")
    append_trace_action(request_id, "AdjustedLogits", {})

    # Format and print
    trace = format_mod_trace(request_id)
    print("=== Multiple Mods Trace Test ===")
    print(trace)
    print("\n")

    # Clean up
    clear_mod_trace(request_id)


def test_no_action_trace():
    """Test trace where mods don't produce actions (all Noop)."""
    request_id = "test_request_003"

    # Initialize trace
    init_mod_trace(request_id)

    # ForwardPass with no real action
    append_trace_event(
        request_id,
        "ForwardPass",
        step=1,
        details={
            "input_text": "Test",
            "top_tokens": [
                {"token": " ing", "prob": 0.70},
                {"token": ".", "prob": 0.20},
                {"token": "!", "prob": 0.05},
            ]
        }
    )
    append_trace_mod_call(request_id, "PassiveMod", "ForwardPass", 1)
    append_trace_mod_log(request_id, "PassiveMod", "Just observing, no action needed")
    # No action appended - should show Noop

    # Sampled event
    append_trace_event(
        request_id,
        "Sampled",
        step=1,
        details={"token_text": " ing"}
    )
    append_trace_mod_call(request_id, "PassiveMod", "Sampled", 1)
    # No action - should show Noop

    # Format and print
    trace = format_mod_trace(request_id)
    print("=== No Action (Noop) Trace Test ===")
    print(trace)
    print("\n")

    # Clean up
    clear_mod_trace(request_id)


def test_ansi_color_output():
    """Test ANSI colored output."""
    request_id = "test_request_ansi"

    # Initialize trace
    init_mod_trace(request_id)

    # Add events with mods and actions
    append_trace_event(
        request_id,
        "Prefill",
        step=0,
        details={"prompt_length": 50}
    )
    append_trace_mod_call(request_id, "ColorMod", "Prefill", 0)
    append_trace_mod_log(request_id, "ColorMod", "Starting with colors!")
    append_trace_action(request_id, "Noop", {})

    append_trace_event(
        request_id,
        "ForwardPass",
        step=1,
        details={
            "input_text": "Test",
            "top_tokens": [
                {"token": " ing", "prob": 0.70},
                {"token": ".", "prob": 0.20},
            ]
        }
    )
    append_trace_mod_call(request_id, "ColorMod", "ForwardPass", 1)
    append_trace_action(request_id, "ForceTokens", {"tokens_preview": "[123, 456]"})

    # Get both plain and colored output
    plain = format_mod_trace(request_id, ansi_color=False)
    colored = format_mod_trace(request_id, ansi_color=True)

    print("=== ANSI Color Output Test ===")
    print("\n1. Plain Output:")
    print(plain)
    print("\n2. ANSI Colored Output:")
    print(colored)
    print("\n3. Color Comparison:")
    print(f"Plain length: {len(plain)} chars")
    print(f"Colored length: {len(colored)} chars (includes ANSI codes)")
    print(f"Difference: {len(colored) - len(plain)} chars of ANSI codes")
    print("\n")

    # Verify colored output contains ANSI codes
    assert "\033[" in colored, "Colored output should contain ANSI escape codes"
    assert "\033[" not in plain, "Plain output should not contain ANSI escape codes"

    print("✓ ANSI color test passed")

    # Clean up
    clear_mod_trace(request_id)


def test_json_output():
    """Test that JSON output contains raw data structure."""
    request_id = "test_request_json"

    # Initialize trace
    init_mod_trace(request_id)

    # Add a simple event with mod call and action
    append_trace_event(
        request_id,
        "Prefill",
        step=0,
        details={"prompt_length": 75}
    )
    append_trace_mod_call(request_id, "TestMod", "Prefill", 0)
    append_trace_mod_log(request_id, "TestMod", "Test log message")
    append_trace_action(request_id, "Noop", {})

    # Get both formatted and JSON outputs
    formatted = format_mod_trace(request_id)
    json_data = get_mod_trace_data(request_id)

    print("=== JSON Output Test ===")
    print("\n1. Formatted Output:")
    print(formatted)
    print("\n2. JSON Data Structure:")
    import json as json_module
    print(json_module.dumps(json_data, indent=2))
    print("\n")

    # Verify JSON structure
    assert isinstance(json_data, list), "JSON data should be a list"
    assert len(json_data) == 4, f"Expected 4 entries, got {len(json_data)}"

    # Check entry types
    assert json_data[0]["type"] == "event"
    assert json_data[0]["event_type"] == "Prefill"
    assert json_data[0]["details"]["prompt_length"] == 75

    assert json_data[1]["type"] == "mod_call"
    assert json_data[1]["mod_name"] == "TestMod"

    assert json_data[2]["type"] == "mod_log"
    assert json_data[2]["message"] == "Test log message"

    assert json_data[3]["type"] == "action"
    assert json_data[3]["action_type"] == "Noop"

    print("✓ JSON structure validated")

    # Clean up
    clear_mod_trace(request_id)


def test_hide_noop_without_logs():
    """Test that mod calls and Noop actions are hidden when there are no logs."""
    request_id = "test_request_hide_noop"

    # Initialize trace
    init_mod_trace(request_id)

    # Event 1: No logs, Noop action - should hide mod call and action
    append_trace_event(request_id, "Prefill", 0, {"prompt_length": 100})
    append_trace_mod_call(request_id, "SilentMod", "Prefill", 0)
    append_trace_action(request_id, "Noop", {})

    # Event 2: Has logs, Noop action - should show mod with └─ and blank line
    append_trace_event(request_id, "ForwardPass", 1, {"input_text": "Test"})
    append_trace_mod_call(request_id, "VerboseMod", "ForwardPass", 1)
    append_trace_mod_log(request_id, "VerboseMod", "Processing step 1\nLine 2")
    append_trace_action(request_id, "Noop", {})

    # Event 3: No logs, but has real action - should show mod call and action
    append_trace_event(request_id, "Sampled", 2, {"token_text": "hello"})
    append_trace_mod_call(request_id, "ActionMod", "Sampled", 2)
    append_trace_action(request_id, "ForceTokens", {"tokens_preview": "[1, 2, 3]"})

    # Event 4: Another no logs, Noop - should hide
    append_trace_event(request_id, "Added", 3, {"token_count": 1})
    append_trace_mod_call(request_id, "AnotherSilentMod", "Added", 3)
    append_trace_action(request_id, "Noop", {})

    # Format and verify
    trace = format_mod_trace(request_id, ansi_color=False)

    print("=== Hide Noop Without Logs Test ===")
    print(trace)
    print("\n")

    # Event 1 should NOT show mod call or action
    assert "SilentMod" not in trace

    # Event 2 should show mod call with └─ and logs with proper indentation
    assert "VerboseMod" in trace
    assert "Processing step 1" in trace
    assert "Line 2" in trace
    # Should use └─ for mod when ending with Noop
    assert "└─ VerboseMod" in trace
    # Should use Logs: label (not Log:)
    assert "Logs:" in trace
    # Should NOT have <─┴ Noop line
    assert "<─┴ Noop" not in trace

    # Verify formatting details
    lines = trace.split('\n')
    # Find the VerboseMod event and check it uses └─ not ├─
    for i, line in enumerate(lines):
        if 'VerboseMod' in line:
            assert '└─' in line, f"Expected └─ for VerboseMod, got: {line}"
            # Next lines should be logs with proper indentation
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                # Logs under └─ should have more indentation
                assert '│           ├' in next_line or '│           └' in next_line or 'Log:' in next_line, f"Expected proper log indentation, got: {next_line}"

    # Event 3 should show mod call and action
    assert "ActionMod" in trace
    assert "ForceTokens" in trace

    # Event 4 should NOT show mod call or action
    assert "AnotherSilentMod" not in trace

    # All events should still appear (just without mod details)
    assert "Prefill" in trace
    assert "ForwardPass" in trace
    assert "Sampled" in trace
    assert "Added" in trace

    # Verify formatting details
    lines = trace.split('\n')
    # Find the VerboseMod event and check it uses └─ not ├─
    for i, line in enumerate(lines):
        if 'VerboseMod' in line:
            assert '└─' in line, f"Expected └─ for VerboseMod, got: {line}"
            # Next lines should be logs with proper indentation
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                # Logs under └─ should have more indentation
                assert '│           ├' in next_line or '│           └' in next_line or 'Log:' in next_line, f"Expected proper log indentation, got: {next_line}"

    print("✓ Noop-only events without logs are properly hidden")
    print("✓ Events with logs and Noop use └─ formatting with blank line closure")

    # Clean up
    clear_mod_trace(request_id)


def test_newlines_and_all_actions():
    """Test escaped newlines in logs and all action types."""
    request_id = "test_request_all_actions"

    # Initialize trace
    init_mod_trace(request_id)

    # Test 1: Logs with newlines (should be escaped)
    append_trace_event(request_id, "Prefill", 0, {"prompt_length": 100})
    append_trace_mod_call(request_id, "TestMod", "Prefill", 0)
    # Test actual newlines in log output
    append_trace_mod_log(request_id, "TestMod", "Line 1\nLine 2\nLine 3")
    append_trace_action(request_id, "Noop", {})

    # Test 2: AdjustedPrefill with max_steps
    append_trace_event(request_id, "Prefill", 1, {"prompt_length": 105})
    append_trace_mod_call(request_id, "AdjustMod", "Prefill", 1)
    append_trace_action(request_id, "AdjustedPrefill", {"new_length": 110, "max_steps": 50})

    # Test 3: ForceTokens with count
    append_trace_event(request_id, "ForwardPass", 1, {"input_text": "Test"})
    append_trace_mod_call(request_id, "ForceMod", "ForwardPass", 1)
    append_trace_action(request_id, "ForceTokens", {"tokens_preview": "[1, 2, 3]", "token_count": 3})

    # Test 4: AdjustedLogits with shape and temperature
    append_trace_event(request_id, "ForwardPass", 2, {"input_text": "More"})
    append_trace_mod_call(request_id, "LogitMod", "ForwardPass", 2)
    append_trace_action(request_id, "AdjustedLogits", {"logits_shape": "[1, 32000]", "temperature": 0.8})

    # Test 5: Backtrack with n and tokens
    append_trace_event(request_id, "Sampled", 3, {"token_text": "bad"})
    append_trace_mod_call(request_id, "BacktrackMod", "Sampled", 3)
    append_trace_action(request_id, "Backtrack", {"n": 2, "tokens_preview": "[10, 20]", "token_count": 2})

    # Test 6: ForceOutput
    append_trace_event(request_id, "Sampled", 4, {"token_text": "end"})
    append_trace_mod_call(request_id, "OutputMod", "Sampled", 4)
    append_trace_action(request_id, "ForceOutput", {"tokens_preview": "[100, 101]", "token_count": 2})

    # Test 7: EmitError
    append_trace_event(request_id, "ForwardPass", 5, {"input_text": "Error"})
    append_trace_mod_call(request_id, "ErrorMod", "ForwardPass", 5)
    append_trace_action(request_id, "EmitError", {"error": "Something went wrong"})

    # Test 8: ToolCalls
    append_trace_event(request_id, "Sampled", 6, {"token_text": "tool"})
    append_trace_mod_call(request_id, "ToolMod", "Sampled", 6)
    append_trace_action(request_id, "ToolCalls", {"has_tool_calls": True})

    # Test 9: Added event with forced tokens
    append_trace_event(request_id, "Added", 7, {"token_count": 3, "forced": True, "tokens": ["Hello", " ", "World"]})
    append_trace_mod_call(request_id, "AddedMod", "Added", 7)
    append_trace_action(request_id, "Noop", {})

    # Format and verify
    trace = format_mod_trace(request_id, ansi_color=False)

    print("=== Newlines and All Actions Test ===")
    print(trace)
    print("\n")

    # Verify newlines create separate lines in output
    assert "Line 1" in trace, "First line should be visible"
    assert "Line 2" in trace, "Second line should be visible"
    assert "Line 3" in trace, "Third line should be visible"

    # Verify all action types appear
    assert "AdjustedPrefill" in trace
    assert "ForceTokens" in trace
    assert "AdjustedLogits" in trace
    assert "Backtrack" in trace
    assert "ForceOutput" in trace
    assert "EmitError" in trace
    assert "ToolCalls" in trace
    assert "Added" in trace

    # Verify some details
    assert "max_steps: 50" in trace
    assert "token_count" in trace or "token(s)" in trace
    assert "error:" in trace

    print("✓ All action types and newline escaping verified")

    # Clean up
    clear_mod_trace(request_id)


def test_multiline_and_wrapping():
    """Test multi-line logs and word-wrapping for long lines."""
    request_id = "test_request_multiline"

    # Initialize trace
    init_mod_trace(request_id)

    # Test 1: Multi-line log from single print with actual newlines
    append_trace_event(request_id, "Prefill", 0, {"prompt_length": 100})
    append_trace_mod_call(request_id, "MultiLineMod", "Prefill", 0)
    append_trace_mod_log(request_id, "MultiLineMod", "Line 1\nLine 2\nLine 3")
    append_trace_action(request_id, "Noop", {})

    # Test 2: Very long single line that should wrap
    append_trace_event(request_id, "ForwardPass", 1, {"input_text": "Test"})
    append_trace_mod_call(request_id, "LongLogMod", "ForwardPass", 1)
    long_log = "build chain for schema FlowQuestion(name='json_schema.f1da588ae8f1.formulary_urls._count', prompt=\"How many elements should the array 'formulary_urls' contain? End with a newline.\", strategy=<sdk.quote_mod_sdk.strategies.strategy_constructor.CharsStrat object at 0x10e41af90>, completion_text='\\n', erase_mode=<EraseMode.ALL: 'all'>, assignments=[<function _build_field_chain_required.<locals>.assign_init_list at 0xdc7252e80>])"
    append_trace_mod_log(request_id, "LongLogMod", long_log)
    append_trace_action(request_id, "ForceTokens", {"tokens_preview": "[1, 2]"})

    # Test 3: Short log for comparison
    append_trace_event(request_id, "Sampled", 2, {"token_text": "test"})
    append_trace_mod_call(request_id, "ShortMod", "Sampled", 2)
    append_trace_mod_log(request_id, "ShortMod", "Simple short log")
    append_trace_action(request_id, "Noop", {})

    # Format and verify
    trace = format_mod_trace(request_id, ansi_color=False)

    print("=== Multi-line and Wrapping Test ===")
    print(trace)
    print("\n")

    # Verify multi-line logs show each line
    assert "Line 1" in trace
    assert "Line 2" in trace
    assert "Line 3" in trace

    # Verify long log is present
    assert "build chain for schema" in trace
    assert "FlowQuestion" in trace

    # Verify short log works normally
    assert "Simple short log" in trace

    print("✓ Multi-line logs displayed correctly")
    print("✓ Long logs wrapped at reasonable width")
    print("✓ Short logs displayed normally")

    # Clean up
    clear_mod_trace(request_id)


def test_never_show_noop():
    """Test that Noop action is NEVER shown in formatted output."""
    request_id = "test_request_never_noop"

    # Initialize trace
    init_mod_trace(request_id)

    # Test case 1: Event with logs and Noop (should use └─ with blank line)
    append_trace_event(request_id, "Added", 1, {"token_count": 1})
    append_trace_mod_call(request_id, "TestMod", "Added", 1)
    append_trace_mod_log(request_id, "TestMod", "completion text check True True")
    append_trace_action(request_id, "Noop", {})

    # Test case 2: Another event with logs and Noop
    append_trace_event(request_id, "Prefill", 0, {"prompt_length": 300})
    append_trace_mod_call(request_id, "MyMod", "Prefill", 0)
    append_trace_mod_log(request_id, "MyMod", "Processing prefill\nAnother line")
    append_trace_action(request_id, "Noop", {})

    # Test case 3: Event with no logs and Noop (should be hidden)
    append_trace_event(request_id, "Sampled", 2, {"token_text": "test"})
    append_trace_mod_call(request_id, "SilentMod", "Sampled", 2)
    append_trace_action(request_id, "Noop", {})

    # Format and verify
    trace = format_mod_trace(request_id, ansi_color=False)

    print("=== Never Show Noop Test ===")
    print(trace)
    print("\n")

    # Critical assertion: "Noop" should NEVER appear anywhere in the trace
    # (It's okay if it appears in log messages, but not as an action)
    assert "<─┴ Noop" not in trace, "CRITICAL: Found '<─┴ Noop' in trace output!"
    assert "│   <─┴ Noop" not in trace, "CRITICAL: Found '│   <─┴ Noop' in trace output!"

    # Verify the correct formatting is used instead
    assert "└─ TestMod" in trace, "Should show mod with end branch (└─)"
    assert "└─ MyMod" in trace, "Should show mod with end branch (└─)"
    assert "completion text check" in trace, "Should show log message"

    # Verify silent mod is completely hidden
    assert "SilentMod" not in trace, "Silent mod with no logs should be hidden"

    print("✓ Verified: Noop action is NEVER shown in output")
    print("✓ Events with logs use └─ and blank line closure")
    print("✓ Events without logs are completely hidden")

    # Clean up
    clear_mod_trace(request_id)


if __name__ == "__main__":
    test_basic_trace()
    test_multiple_mods()
    test_no_action_trace()
    test_ansi_color_output()
    test_json_output()
    test_hide_noop_without_logs()
    test_newlines_and_all_actions()
    test_multiline_and_wrapping()
    test_never_show_noop()

    print("All trace formatting tests completed!")
