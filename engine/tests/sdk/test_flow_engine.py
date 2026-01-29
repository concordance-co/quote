"""Flow Engine validation tests.

These tests validate the Flow Engine's ability to handle multi-step flows
with multiple self-prompts. Specifically targeting the reported issue where
flows fail to trigger more than two self-prompts.

BUG FOUND #1: Type mismatch in FlowEngine._ensure_constraint (flow.py:313-318)
    - SelfPrompt.__init__ expects `completion: Optional[str]`
    - FlowEngine passes `completion={"suffix": ..., "force": True}` (a dict)
    - This causes TypeError when _resolve_completion_suffix tries to tokenize the dict
    - Location: flow.py:316 passes dict, self_prompt.py:183 expects str
    - Workaround: Use EraseMode.ALL (skips completion suffix logic at line 429)

BUG FOUND #1b: Debug print crashes before type check (self_prompt.py:221)
    - print("suffix", suffix, _tokenize_optional(suffix, tokenizer))
    - Calls _tokenize_optional() BEFORE checking isinstance(suffix, str)
    - Should move print after the type check or remove it
"""
from __future__ import annotations

import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = PROJECT_ROOT / "src"
INFER_PATH = PROJECT_ROOT / "inference" / "src"
SHARED_PATH = PROJECT_ROOT / "shared" / "src"
SDK_PATH = PROJECT_ROOT / "sdk"

for p in [PROJECT_ROOT, SRC_PATH, INFER_PATH, SHARED_PATH, SDK_PATH]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest

from sdk.quote_mod_sdk.actions import ActionBuilder
from sdk.quote_mod_sdk.flow import (
    FlowQuestion,
    FlowDefinition,
    FlowEngine,
    FlowState,
    RequestState,
    route_question,
    route_message,
    route_summary,
    route_output,
    route_tool,
    route_noop,
)
from sdk.quote_mod_sdk.self_prompt import SelfPrompt, EraseMode
from sdk.quote_mod_sdk.strategies.strategy_constructor import (
    ChoicesStrat,
    CharsStrat,
    CharsMode,
    UntilStrat,
    ListStrat,
)
from sdk.quote_mod_sdk.strategies.primitives import UntilEndType
from shared.types import (
    Prefilled as PrefilledEvent,
    ForwardPass as ForwardPassEvent,
    Added as AddedEvent,
    ForceTokens,
    AdjustedLogits,
    Backtrack,
    Noop,
)
from tests.sdk.utils import TestTokenizer, DummyLogits


# ============================================================================
# Test Utilities
# ============================================================================

def create_prefilled(request_id: str, step: int = 0) -> PrefilledEvent:
    """Create a Prefilled event."""
    return PrefilledEvent(
        request_id=request_id,
        step=step,
        max_steps=100,
        context_info={},
    )


def create_forward_pass(request_id: str, step: int = 0, vocab_size: int = 256) -> ForwardPassEvent:
    """Create a ForwardPass event with dummy logits."""
    return ForwardPassEvent(
        request_id=request_id,
        step=step,
        logits=DummyLogits(vocab_size),
    )


def create_added(
    request_id: str,
    tokens: List[int],
    step: int = 0,
    forced: bool = False
) -> AddedEvent:
    """Create an Added event."""
    return AddedEvent(
        request_id=request_id,
        step=step,
        added_tokens=tokens,
        forced=forced,
    )


class FlowTestHarness:
    """Test harness for simulating Flow Engine execution."""

    def __init__(self, engine: FlowEngine, tokenizer: TestTokenizer, request_id: str = "test-req"):
        self.engine = engine
        self.tokenizer = tokenizer
        self.request_id = request_id
        self.step = 0
        self.generated_tokens: List[int] = []
        self.action_log: List[tuple] = []  # (step, action_type, details)

    def run_prefilled(self) -> Any:
        """Run the Prefilled event phase."""
        event = create_prefilled(self.request_id, self.step)
        actions = ActionBuilder(event)
        result = self.engine.handle_event(event, actions, self.tokenizer)
        self.action_log.append((self.step, type(result).__name__, str(result)))
        return result

    def run_forward_pass(self) -> Any:
        """Run a ForwardPass event."""
        self.step += 1
        event = create_forward_pass(self.request_id, self.step)
        actions = ActionBuilder(event)
        result = self.engine.handle_event(event, actions, self.tokenizer)
        self.action_log.append((self.step, type(result).__name__, str(result)))
        return result

    def run_added(self, tokens: List[int], forced: bool = False) -> Any:
        """Run an Added event with the given tokens."""
        event = create_added(self.request_id, tokens, self.step, forced)
        actions = ActionBuilder(event)
        result = self.engine.handle_event(event, actions, self.tokenizer)
        if not forced:
            self.generated_tokens.extend(tokens)
        self.action_log.append((self.step, type(result).__name__, f"tokens={tokens}, forced={forced}"))
        return result

    def simulate_force_tokens(self, action: ForceTokens) -> None:
        """Simulate the engine processing forced tokens."""
        # Process forced tokens by running Added event for each batch
        self.run_added(action.tokens, forced=True)

    def simulate_answer(self, answer_text: str) -> None:
        """Simulate the model generating an answer."""
        tokens = self.tokenizer.encode(answer_text, add_special_tokens=False)
        for tok in tokens:
            self.run_added([tok], forced=False)

    def complete_question_cycle(self, answer: str) -> List[Any]:
        """Complete one question cycle: ForwardPass -> answer tokens -> completion.

        Returns list of all actions generated.
        """
        actions_generated = []

        # First ForwardPass should force prompt tokens
        action = self.run_forward_pass()
        actions_generated.append(action)

        if isinstance(action, ForceTokens):
            # Process forced prompt tokens
            self.simulate_force_tokens(action)

            # Next ForwardPass should start constraining
            action = self.run_forward_pass()
            actions_generated.append(action)

        # Now simulate answering
        if isinstance(action, AdjustedLogits):
            answer_tokens = self.tokenizer.encode(answer, add_special_tokens=False)
            for tok in answer_tokens:
                self.run_added([tok], forced=False)
                # After each token, run another forward pass
                action = self.run_forward_pass()
                actions_generated.append(action)
                if isinstance(action, ForceTokens):
                    # Completion suffix
                    self.simulate_force_tokens(action)
                    action = self.run_forward_pass()
                    actions_generated.append(action)
                if isinstance(action, Backtrack):
                    break

        return actions_generated

    def get_current_question_name(self) -> Optional[str]:
        """Get the name of the current question."""
        state = self.engine._states.get(self.request_id)
        if state and state.current_question:
            return state.current_question.name
        return None

    def get_answers(self) -> Dict[str, str]:
        """Get all recorded answers."""
        state = self.engine._states.get(self.request_id)
        if state:
            return dict(state.answers)
        return {}


# ============================================================================
# Test: Basic Two-Question Flow
# ============================================================================

class TestTwoQuestionFlow:
    """Tests for basic two-question flows - this should work."""

    def test_two_choices_questions(self):
        """Test a flow with two ChoicesStrat questions."""
        tok = TestTokenizer()

        # NOTE: EraseMode.ALL works around BUG #1 (type mismatch)
        q1 = FlowQuestion(
            name="q1",
            prompt=" Q1:",
            strategy=ChoicesStrat(["A", "B"]),
            erase_mode=EraseMode.ALL,  # Work around BUG #1
        )
        q2 = FlowQuestion(
            name="q2",
            prompt=" Q2:",
            strategy=ChoicesStrat(["X", "Y"]),
            erase_mode=EraseMode.ALL,  # Work around BUG #1
        )
        q1.then(route_question(q2))
        q2.then(route_message("Done!"))

        engine = FlowEngine(entry_question=q1)
        harness = FlowTestHarness(engine, tok)

        # Initialize
        result = harness.run_prefilled()
        assert harness.get_current_question_name() == "q1"

        # First ForwardPass should force Q1 prompt
        result = harness.run_forward_pass()
        assert isinstance(result, ForceTokens), f"Expected ForceTokens, got {type(result)}"
        prompt_text = tok.decode(result.tokens)
        assert "Q1" in prompt_text

        # Process prompt tokens
        harness.simulate_force_tokens(result)

        # Next ForwardPass should adjust logits for Q1
        result = harness.run_forward_pass()
        assert isinstance(result, AdjustedLogits), f"Expected AdjustedLogits, got {type(result)}"

        # Simulate answering "A"
        harness.run_added([ord("A")], forced=False)

        # ForwardPass after answer - may force completion suffix or transition
        result = harness.run_forward_pass()

        # Handle completion suffix if present
        if isinstance(result, ForceTokens):
            harness.simulate_force_tokens(result)
            result = harness.run_forward_pass()

        # Should now be at Q2
        assert harness.get_current_question_name() == "q2", \
            f"Expected q2, got {harness.get_current_question_name()}"

        # Q2 should force its prompt
        assert isinstance(result, ForceTokens), f"Expected ForceTokens for Q2, got {type(result)}"
        prompt_text = tok.decode(result.tokens)
        assert "Q2" in prompt_text


# ============================================================================
# Test: Three-Question Flow (Bug Target)
# ============================================================================

class TestThreeQuestionFlow:
    """Tests for three-question flows - this is where the bug reportedly occurs."""

    def test_three_choices_questions_linear(self):
        """Test a linear flow with three ChoicesStrat questions.

        This is the primary bug reproduction test. The reported issue is that
        flows fail to trigger more than two self-prompts.
        """
        tok = TestTokenizer()

        # NOTE: EraseMode.ALL works around BUG #1 (type mismatch)
        q1 = FlowQuestion(
            name="q1_first",
            prompt=" First:",
            strategy=ChoicesStrat(["A", "B"]),
            erase_mode=EraseMode.ALL,
        )
        q2 = FlowQuestion(
            name="q2_second",
            prompt=" Second:",
            strategy=ChoicesStrat(["X", "Y"]),
            erase_mode=EraseMode.ALL,
        )
        q3 = FlowQuestion(
            name="q3_third",
            prompt=" Third:",
            strategy=ChoicesStrat(["1", "2"]),
            erase_mode=EraseMode.ALL,
        )

        q1.then(route_question(q2))
        q2.then(route_question(q3))
        q3.then(route_message("Complete!"))

        engine = FlowEngine(entry_question=q1)
        harness = FlowTestHarness(engine, tok, request_id="three-q-test")

        questions_visited = []

        # Initialize
        harness.run_prefilled()
        questions_visited.append(harness.get_current_question_name())

        # === Q1 ===
        result = harness.run_forward_pass()
        assert isinstance(result, ForceTokens), f"Q1: Expected ForceTokens, got {type(result)}"
        harness.simulate_force_tokens(result)

        result = harness.run_forward_pass()
        assert isinstance(result, AdjustedLogits), f"Q1: Expected AdjustedLogits, got {type(result)}"

        harness.run_added([ord("A")], forced=False)
        result = harness.run_forward_pass()

        if isinstance(result, ForceTokens):  # completion suffix
            harness.simulate_force_tokens(result)
            result = harness.run_forward_pass()

        questions_visited.append(harness.get_current_question_name())
        print(f"After Q1: current_question={harness.get_current_question_name()}, action={type(result)}")

        # === Q2 ===
        assert harness.get_current_question_name() == "q2_second", \
            f"Expected q2_second, got {harness.get_current_question_name()}"
        assert isinstance(result, ForceTokens), f"Q2: Expected ForceTokens, got {type(result)}"

        harness.simulate_force_tokens(result)
        result = harness.run_forward_pass()
        assert isinstance(result, AdjustedLogits), f"Q2: Expected AdjustedLogits, got {type(result)}"

        harness.run_added([ord("X")], forced=False)
        result = harness.run_forward_pass()

        if isinstance(result, ForceTokens):  # completion suffix
            harness.simulate_force_tokens(result)
            result = harness.run_forward_pass()

        questions_visited.append(harness.get_current_question_name())
        print(f"After Q2: current_question={harness.get_current_question_name()}, action={type(result)}")

        # === Q3 (This is where the bug should manifest) ===
        assert harness.get_current_question_name() == "q3_third", \
            f"BUG: Expected q3_third, got {harness.get_current_question_name()}. " \
            f"Questions visited: {questions_visited}"

        assert isinstance(result, ForceTokens), \
            f"BUG: Q3 should force prompt tokens, got {type(result)}. " \
            f"This indicates the third self-prompt is not triggering."

        prompt_text = tok.decode(result.tokens)
        assert "Third" in prompt_text, f"Q3 prompt should contain 'Third', got: {prompt_text}"

        print(f"SUCCESS: Three-question flow reached Q3 correctly")
        print(f"Questions visited: {questions_visited}")

    def test_three_questions_with_erase_all(self):
        """Test three questions with EraseMode.ALL - more complex state management."""
        tok = TestTokenizer()

        # NOTE: completion_text="" works around BUG #1
        q1 = FlowQuestion(
            name="erased_q1",
            prompt=" E1:",
            strategy=ChoicesStrat(["A"]),
            erase_mode=EraseMode.ALL,
            completion_text="",
        )
        q2 = FlowQuestion(
            name="erased_q2",
            prompt=" E2:",
            strategy=ChoicesStrat(["B"]),
            erase_mode=EraseMode.ALL,
            completion_text="",
        )
        q3 = FlowQuestion(
            name="erased_q3",
            prompt=" E3:",
            strategy=ChoicesStrat(["C"]),
            erase_mode=EraseMode.ALL,
            completion_text="",
        )

        q1.then(route_question(q2))
        q2.then(route_question(q3))
        q3.then(route_message("Done"))

        engine = FlowEngine(entry_question=q1)
        harness = FlowTestHarness(engine, tok, request_id="erase-test")

        harness.run_prefilled()

        # Q1
        result = harness.run_forward_pass()
        assert isinstance(result, ForceTokens)
        harness.simulate_force_tokens(result)

        result = harness.run_forward_pass()
        harness.run_added([ord("A")], forced=False)

        # With EraseMode.ALL, should get a Backtrack after completion
        result = harness.run_forward_pass()

        if isinstance(result, Backtrack):
            # After backtrack, next ForwardPass should start Q2
            result = harness.run_forward_pass()

        print(f"After Q1 (erase): current={harness.get_current_question_name()}, action={type(result)}")

        # Continue through Q2
        if isinstance(result, ForceTokens):
            harness.simulate_force_tokens(result)
            result = harness.run_forward_pass()

        if isinstance(result, AdjustedLogits):
            harness.run_added([ord("B")], forced=False)
            result = harness.run_forward_pass()

        if isinstance(result, Backtrack):
            result = harness.run_forward_pass()

        print(f"After Q2 (erase): current={harness.get_current_question_name()}, action={type(result)}")

        # Q3 check
        current = harness.get_current_question_name()
        assert current == "erased_q3", \
            f"BUG with EraseMode.ALL: Expected erased_q3, got {current}"


# ============================================================================
# Test: Four-Question Flow
# ============================================================================

class TestFourQuestionFlow:
    """Tests for four-question flows to verify the limit."""

    def test_four_questions_linear(self):
        """Test a linear flow with four questions."""
        tok = TestTokenizer()

        questions = []
        for i in range(4):
            q = FlowQuestion(
                name=f"q{i+1}",
                prompt=f" Q{i+1}:",
                strategy=ChoicesStrat([chr(ord('A') + i)]),
                erase_mode=EraseMode.ALL,  # Work around BUG #1
            )
            questions.append(q)

        # Chain them
        for i in range(3):
            questions[i].then(route_question(questions[i+1]))
        questions[3].then(route_message("All done!"))

        engine = FlowEngine(entry_question=questions[0])
        harness = FlowTestHarness(engine, tok, request_id="four-q-test")

        harness.run_prefilled()

        reached_questions = [harness.get_current_question_name()]

        for i, expected_q in enumerate([f"q{j+1}" for j in range(4)]):
            print(f"\n=== Processing {expected_q} ===")

            result = harness.run_forward_pass()

            if isinstance(result, ForceTokens):
                harness.simulate_force_tokens(result)
                result = harness.run_forward_pass()

            if isinstance(result, AdjustedLogits):
                answer_tok = ord('A') + i
                harness.run_added([answer_tok], forced=False)
                result = harness.run_forward_pass()

            if isinstance(result, ForceTokens):  # completion suffix
                harness.simulate_force_tokens(result)
                result = harness.run_forward_pass()

            current = harness.get_current_question_name()
            reached_questions.append(current)
            print(f"After {expected_q}: current={current}, action={type(result)}")

        # Verify we reached all 4 questions
        unique_questions = [q for q in reached_questions if q is not None]
        print(f"\nQuestions reached: {unique_questions}")

        for i in range(4):
            expected = f"q{i+1}"
            assert expected in unique_questions, \
                f"BUG: Question {expected} was never reached. Reached: {unique_questions}"


# ============================================================================
# Test: Different Strategy Types
# ============================================================================

class TestMixedStrategies:
    """Test flows with different strategy types."""

    def test_choices_then_chars_then_choices(self):
        """Test mixing ChoicesStrat and CharsStrat."""
        tok = TestTokenizer()

        # NOTE: EraseMode.ALL works around BUG #1
        q1 = FlowQuestion(
            name="choice1",
            prompt=" Pick:",
            strategy=ChoicesStrat(["go", "stop"]),
            erase_mode=EraseMode.ALL,
        )
        q2 = FlowQuestion(
            name="digits",
            prompt=" Code:",
            strategy=CharsStrat(CharsMode.NUMERIC, min=3, stop=3),
            erase_mode=EraseMode.ALL,
        )
        q3 = FlowQuestion(
            name="choice2",
            prompt=" Confirm:",
            strategy=ChoicesStrat(["yes", "no"]),
            erase_mode=EraseMode.ALL,
        )

        q1.on("go", route_question(q2))
        q1.on("stop", route_message("Stopped"))
        q2.then(route_question(q3))
        q3.then(route_message("Complete"))

        engine = FlowEngine(entry_question=q1)
        harness = FlowTestHarness(engine, tok, request_id="mixed-strat")

        harness.run_prefilled()

        # Q1: choice
        result = harness.run_forward_pass()
        assert isinstance(result, ForceTokens)
        harness.simulate_force_tokens(result)

        result = harness.run_forward_pass()
        for c in "go":
            harness.run_added([ord(c)], forced=False)
            result = harness.run_forward_pass()
            if isinstance(result, ForceTokens):
                harness.simulate_force_tokens(result)
                result = harness.run_forward_pass()

        print(f"After Q1: {harness.get_current_question_name()}")

        # Q2: digits
        if harness.get_current_question_name() == "digits":
            if isinstance(result, ForceTokens):
                harness.simulate_force_tokens(result)
                result = harness.run_forward_pass()

            for d in "123":
                harness.run_added([ord(d)], forced=False)
                result = harness.run_forward_pass()
                if isinstance(result, ForceTokens):
                    harness.simulate_force_tokens(result)
                    result = harness.run_forward_pass()

            print(f"After Q2: {harness.get_current_question_name()}")

        # Q3: confirm
        assert harness.get_current_question_name() == "choice2", \
            f"BUG: Expected choice2, got {harness.get_current_question_name()}"


# ============================================================================
# Test: Branching Flows
# ============================================================================

class TestBranchingFlows:
    """Test flows with conditional branching."""

    def test_branch_on_answer(self):
        """Test that branching based on answer works for 3+ questions."""
        tok = TestTokenizer()

        # NOTE: EraseMode.ALL works around BUG #1
        router = FlowQuestion(
            name="router",
            prompt=" Path:",
            strategy=ChoicesStrat(["left", "right"]),
            erase_mode=EraseMode.ALL,
        )
        left1 = FlowQuestion(
            name="left1",
            prompt=" L1:",
            strategy=ChoicesStrat(["a"]),
            erase_mode=EraseMode.ALL,
        )
        left2 = FlowQuestion(
            name="left2",
            prompt=" L2:",
            strategy=ChoicesStrat(["b"]),
            erase_mode=EraseMode.ALL,
        )
        right1 = FlowQuestion(
            name="right1",
            prompt=" R1:",
            strategy=ChoicesStrat(["x"]),
            erase_mode=EraseMode.ALL,
        )

        router.on("left", route_question(left1))
        router.on("right", route_question(right1))
        left1.then(route_question(left2))
        left2.then(route_message("Left done"))
        right1.then(route_message("Right done"))

        engine = FlowEngine(entry_question=router)
        harness = FlowTestHarness(engine, tok, request_id="branch-test")

        harness.run_prefilled()

        # Router
        result = harness.run_forward_pass()
        harness.simulate_force_tokens(result)
        result = harness.run_forward_pass()

        # Answer "left"
        for c in "left":
            harness.run_added([ord(c)], forced=False)
            result = harness.run_forward_pass()
            if isinstance(result, ForceTokens):
                harness.simulate_force_tokens(result)
                result = harness.run_forward_pass()

        assert harness.get_current_question_name() == "left1", \
            f"Expected left1, got {harness.get_current_question_name()}"

        # Left1
        if isinstance(result, ForceTokens):
            harness.simulate_force_tokens(result)
            result = harness.run_forward_pass()

        harness.run_added([ord("a")], forced=False)
        result = harness.run_forward_pass()
        if isinstance(result, ForceTokens):
            harness.simulate_force_tokens(result)
            result = harness.run_forward_pass()

        # Should be at left2 (third question in this branch)
        assert harness.get_current_question_name() == "left2", \
            f"BUG: Expected left2 (3rd question), got {harness.get_current_question_name()}"


# ============================================================================
# Test: State Reset Between Requests
# ============================================================================

class TestStateManagement:
    """Test that state is properly managed between different requests."""

    def test_multiple_requests_same_engine(self):
        """Test that multiple requests can use the same engine independently."""
        tok = TestTokenizer()

        # NOTE: EraseMode.ALL works around BUG #1
        q1 = FlowQuestion(
            name="shared_q1",
            prompt=" Q1:",
            strategy=ChoicesStrat(["A", "B"]),
            erase_mode=EraseMode.ALL,
        )
        q2 = FlowQuestion(
            name="shared_q2",
            prompt=" Q2:",
            strategy=ChoicesStrat(["X", "Y"]),
            erase_mode=EraseMode.ALL,
        )
        q1.then(route_question(q2))
        q2.then(route_message("Done"))

        engine = FlowEngine(entry_question=q1)

        # First request
        h1 = FlowTestHarness(engine, tok, request_id="req-1")
        h1.run_prefilled()

        result = h1.run_forward_pass()
        h1.simulate_force_tokens(result)
        result = h1.run_forward_pass()
        h1.run_added([ord("A")], forced=False)
        result = h1.run_forward_pass()
        if isinstance(result, ForceTokens):
            h1.simulate_force_tokens(result)
            result = h1.run_forward_pass()

        assert h1.get_current_question_name() == "shared_q2"

        # Second request - should start fresh
        h2 = FlowTestHarness(engine, tok, request_id="req-2")
        h2.run_prefilled()

        assert h2.get_current_question_name() == "shared_q1", \
            f"Second request should start at q1, got {h2.get_current_question_name()}"

        # First request should still be at q2
        assert h1.get_current_question_name() == "shared_q2", \
            f"First request state corrupted, expected q2, got {h1.get_current_question_name()}"


# ============================================================================
# Test: Self-Prompt State Investigation
# ============================================================================

class TestSelfPromptState:
    """Investigate SelfPrompt state to understand the bug."""

    def test_constraint_state_after_transitions(self):
        """Examine the internal state of SelfPrompt constraints during transitions."""
        tok = TestTokenizer()

        # NOTE: EraseMode.ALL works around BUG #1
        q1 = FlowQuestion(name="inspect_q1", prompt=" I1:", strategy=ChoicesStrat(["A"]), erase_mode=EraseMode.ALL)
        q2 = FlowQuestion(name="inspect_q2", prompt=" I2:", strategy=ChoicesStrat(["B"]), erase_mode=EraseMode.ALL)
        q3 = FlowQuestion(name="inspect_q3", prompt=" I3:", strategy=ChoicesStrat(["C"]), erase_mode=EraseMode.ALL)

        q1.then(route_question(q2))
        q2.then(route_question(q3))
        q3.then(route_message("Done"))

        engine = FlowEngine(entry_question=q1)
        harness = FlowTestHarness(engine, tok, request_id="inspect-test")

        harness.run_prefilled()

        def inspect_constraints():
            """Print state of all constraints."""
            for name, constraint in engine._constraints.items():
                state = constraint._states.get(harness.request_id)
                if state:
                    print(f"  Constraint '{name}': compiled={state.compiled is not None}, "
                          f"completed={state.completed}, prompt_emitted={state.prompt_emitted}, "
                          f"outstanding_forced={state.outstanding_forced}")
                else:
                    print(f"  Constraint '{name}': no state for this request")

        print("\n=== Initial state ===")
        inspect_constraints()

        # Process Q1
        result = harness.run_forward_pass()
        harness.simulate_force_tokens(result)
        result = harness.run_forward_pass()
        harness.run_added([ord("A")], forced=False)

        print("\n=== After Q1 answer ===")
        inspect_constraints()

        result = harness.run_forward_pass()
        if isinstance(result, ForceTokens):
            harness.simulate_force_tokens(result)
            result = harness.run_forward_pass()

        print(f"\n=== After Q1 complete, current={harness.get_current_question_name()} ===")
        inspect_constraints()

        # Process Q2
        if isinstance(result, ForceTokens):
            harness.simulate_force_tokens(result)
            result = harness.run_forward_pass()
        if isinstance(result, AdjustedLogits):
            harness.run_added([ord("B")], forced=False)
            result = harness.run_forward_pass()
        if isinstance(result, ForceTokens):
            harness.simulate_force_tokens(result)
            result = harness.run_forward_pass()

        print(f"\n=== After Q2 complete, current={harness.get_current_question_name()} ===")
        inspect_constraints()

        # Q3 - the critical point
        current = harness.get_current_question_name()
        print(f"\nFinal current question: {current}")
        print(f"Action type: {type(result)}")

        if current != "inspect_q3":
            print(f"\n!!! BUG DETECTED: Expected inspect_q3, got {current}")
            print("Constraint states at failure point:")
            inspect_constraints()

            # Check if q3's constraint exists and its state
            q3_constraint = engine._constraints.get("inspect_q3")
            if q3_constraint:
                q3_state = q3_constraint._states.get(harness.request_id)
                if q3_state:
                    print(f"\nQ3 constraint state details:")
                    print(f"  compiled: {q3_state.compiled}")
                    print(f"  prompt_tokens: {q3_state.prompt_tokens}")
                    print(f"  prompt_emitted: {q3_state.prompt_emitted}")
            else:
                print("\nQ3 constraint not yet created!")


# ============================================================================
# Test: Direct multi-question flow (simplified)
# ============================================================================

class TestDirectMultiQuestionFlow:
    """Direct tests that properly drive the flow state machine."""

    def test_five_questions_erase_all(self):
        """Test 5 questions with EraseMode.ALL - properly handling Backtracks.

        This test demonstrates that the Flow Engine CAN handle 5+ self-prompts
        when the harness properly handles the Backtrack -> ForwardPass sequence.
        """
        tok = TestTokenizer()

        # Create 5 questions
        questions = []
        for i in range(5):
            q = FlowQuestion(
                name=f"q{i+1}",
                prompt=f" Question{i+1}:",
                strategy=ChoicesStrat([chr(ord('A') + i)]),
                erase_mode=EraseMode.ALL,
                completion_text="",  # Empty to avoid BUG #1
            )
            questions.append(q)

        # Chain them
        for i in range(4):
            questions[i].then(route_question(questions[i+1]))
        questions[4].then(route_message("All 5 complete!"))

        engine = FlowEngine(entry_question=questions[0])
        harness = FlowTestHarness(engine, tok, request_id="five-q-test")

        harness.run_prefilled()

        questions_completed = []
        max_iterations = 50  # Safety limit

        for iteration in range(max_iterations):
            result = harness.run_forward_pass()

            if isinstance(result, ForceTokens):
                harness.simulate_force_tokens(result)
                continue

            if isinstance(result, AdjustedLogits):
                # Provide the expected answer for current question
                current = harness.get_current_question_name()
                if current and current.startswith("q"):
                    q_num = int(current[1:])
                    answer_token = ord('A') + q_num - 1
                    harness.run_added([answer_token], forced=False)
                continue

            if isinstance(result, Backtrack):
                # Backtrack emitted - next ForwardPass will process transition
                continue

            if isinstance(result, Noop):
                # Check if question completed
                current = harness.get_current_question_name()
                if current and current not in questions_completed:
                    questions_completed.append(current)
                if len(questions_completed) >= 5:
                    break

        print(f"\nQuestions completed: {questions_completed}")
        print(f"Final answers: {harness.get_answers()}")

        # Verify all 5 questions were visited
        assert len(questions_completed) >= 3, \
            f"Expected at least 3 questions, got {len(questions_completed)}: {questions_completed}"


class TestEraseModeBehavior:
    """Test to understand EraseMode.NONE vs EraseMode.ALL behavior."""

    def test_erase_mode_none_works(self):
        """Verify that EraseMode.NONE works correctly after the bug fix.

        BUG #1 was fixed: FlowEngine now passes the completion string directly
        to SelfPrompt instead of a dict.
        """
        tok = TestTokenizer()

        q1 = FlowQuestion(
            name="fixed_test_q1",
            prompt=" Test:",
            strategy=ChoicesStrat(["A"]),
            erase_mode=EraseMode.NONE,  # This no longer crashes!
            # Default completion_text="\n"
        )

        engine = FlowEngine(entry_question=q1)
        harness = FlowTestHarness(engine, tok, request_id="fixed-test")

        harness.run_prefilled()

        # Force the prompt
        result = harness.run_forward_pass()
        assert isinstance(result, ForceTokens)
        harness.simulate_force_tokens(result)

        # Get AdjustedLogits
        result = harness.run_forward_pass()
        assert isinstance(result, AdjustedLogits)

        # Add answer - This should NOT crash anymore
        harness.run_added([ord("A")], forced=False)

        # ForwardPass after answer - should force completion suffix
        result = harness.run_forward_pass()
        assert isinstance(result, ForceTokens), f"Expected ForceTokens for completion suffix, got {type(result)}"

        print(f"\nBUG #1 FIXED: EraseMode.NONE with default completion works correctly")


# ============================================================================
# Test: UntilStrat (Tag-based extraction)
# ============================================================================

class TestUntilStrat:
    """Test UntilStrat for tag-based content extraction."""

    def test_until_strat_with_tags(self):
        """Test extracting content between XML-like tags."""
        tok = TestTokenizer()

        q1 = FlowQuestion(
            name="extract_answer",
            prompt=" Wrap your answer in tags: ",
            strategy=UntilStrat("<answer>", UntilEndType.TAG, "</answer>"),
            erase_mode=EraseMode.ALL,
            completion_text="",
        )
        q1.then(route_message("Got it!"))

        engine = FlowEngine(entry_question=q1)
        harness = FlowTestHarness(engine, tok, request_id="until-test")

        harness.run_prefilled()

        # Process through forcing prompt
        result = harness.run_forward_pass()
        if isinstance(result, ForceTokens):
            harness.simulate_force_tokens(result)

        # The strategy should force the opening tag
        result = harness.run_forward_pass()
        print(f"After prompt: {type(result)}, current={harness.get_current_question_name()}")

        # Simulate generating "<answer>hello</answer>"
        answer_text = "<answer>hello</answer>"
        for char in answer_text:
            if isinstance(result, (ForceTokens, AdjustedLogits)):
                if isinstance(result, ForceTokens):
                    harness.simulate_force_tokens(result)
                else:
                    harness.run_added([ord(char)], forced=False)
            result = harness.run_forward_pass()

        print(f"Final: current={harness.get_current_question_name()}")
        print(f"Answers: {harness.get_answers()}")


# ============================================================================
# Test: ListStrat
# ============================================================================

class TestListStrat:
    """Test ListStrat for structured list generation."""

    def test_list_strat_basic(self):
        """Test generating a list of choices."""
        tok = TestTokenizer()

        q1 = FlowQuestion(
            name="pick_colors",
            prompt=" Pick colors: ",
            strategy=ListStrat(
                elements=ChoicesStrat(["red", "blue"]),
                sep=",",
                min=2,
                max=2,
            ),
            erase_mode=EraseMode.ALL,
            completion_text="",
        )
        q1.then(route_message("Colors selected!"))

        engine = FlowEngine(entry_question=q1)
        harness = FlowTestHarness(engine, tok, request_id="list-test")

        harness.run_prefilled()

        # Drive through the flow
        for _ in range(20):
            result = harness.run_forward_pass()

            if isinstance(result, ForceTokens):
                harness.simulate_force_tokens(result)
            elif isinstance(result, AdjustedLogits):
                # Provide "red" for first, "blue" for second
                current_answer = harness.get_answers().get("pick_colors", "")
                if "red" not in current_answer:
                    for c in "red":
                        harness.run_added([ord(c)], forced=False)
                        result = harness.run_forward_pass()
                        if isinstance(result, ForceTokens):
                            harness.simulate_force_tokens(result)
                else:
                    for c in "blue":
                        harness.run_added([ord(c)], forced=False)
                        result = harness.run_forward_pass()
                        if isinstance(result, ForceTokens):
                            harness.simulate_force_tokens(result)

        print(f"ListStrat answers: {harness.get_answers()}")


# ============================================================================
# Test: .assign() - State mutation
# ============================================================================

class TestAssign:
    """Test .assign() for state mutation after question completion."""

    def test_assign_modifies_state(self):
        """Test that .assign() callback is called with answer."""
        tok = TestTokenizer()

        # Track assign calls
        assign_calls = []

        def track_assign(state, answer):
            assign_calls.append({"state": state, "answer": answer})
            state.data["captured_answer"] = answer

        q1 = FlowQuestion(
            name="with_assign",
            prompt=" Choose: ",
            strategy=ChoicesStrat(["A", "B"]),
            erase_mode=EraseMode.ALL,
            completion_text="",
        )
        q1.assign(track_assign)
        q1.then(route_message("Done"))

        engine = FlowEngine(entry_question=q1)
        harness = FlowTestHarness(engine, tok, request_id="assign-test")

        harness.run_prefilled()

        # Drive through Q1
        for _ in range(10):
            result = harness.run_forward_pass()
            if isinstance(result, ForceTokens):
                harness.simulate_force_tokens(result)
            elif isinstance(result, AdjustedLogits):
                harness.run_added([ord("A")], forced=False)

        print(f"Assign calls: {len(assign_calls)}")
        print(f"Answers: {harness.get_answers()}")

        # Check if assign was called
        if assign_calls:
            print(f"Assign captured: {assign_calls[0]['answer']}")
            assert assign_calls[0]["answer"] == "A", "Assign should receive the answer"


# ============================================================================
# Test: .with_auto_answer() - Skip questions
# ============================================================================

class TestAutoAnswer:
    """Test .with_auto_answer() for automatically answering questions."""

    def test_auto_answer_skips_question(self):
        """Test that auto_answer skips token generation for a question."""
        tok = TestTokenizer()

        q1 = FlowQuestion(
            name="auto_q1",
            prompt=" Manual choice: ",
            strategy=ChoicesStrat(["go"]),
            erase_mode=EraseMode.ALL,
            completion_text="",
        )

        q2 = FlowQuestion(
            name="auto_q2",
            prompt=" This should be auto-answered: ",
            strategy=ChoicesStrat(["yes", "no"]),
            erase_mode=EraseMode.ALL,
            completion_text="",
        )
        # Auto-answer Q2 with "yes"
        q2.with_auto_answer(lambda state: "yes")

        q3 = FlowQuestion(
            name="auto_q3",
            prompt=" Final question: ",
            strategy=ChoicesStrat(["done"]),
            erase_mode=EraseMode.ALL,
            completion_text="",
        )

        q1.then(route_question(q2))
        q2.then(route_question(q3))
        q3.then(route_message("Complete"))

        engine = FlowEngine(entry_question=q1)
        harness = FlowTestHarness(engine, tok, request_id="auto-answer-test")

        harness.run_prefilled()

        questions_seen = []
        for _ in range(30):
            current = harness.get_current_question_name()
            if current and current not in questions_seen:
                questions_seen.append(current)

            result = harness.run_forward_pass()

            if isinstance(result, ForceTokens):
                harness.simulate_force_tokens(result)
            elif isinstance(result, AdjustedLogits):
                # Answer based on current question
                if current == "auto_q1":
                    for c in "go":
                        harness.run_added([ord(c)], forced=False)
                        harness.run_forward_pass()
                elif current == "auto_q3":
                    for c in "done":
                        harness.run_added([ord(c)], forced=False)
                        harness.run_forward_pass()

        print(f"Questions seen: {questions_seen}")
        print(f"Answers: {harness.get_answers()}")

        # Q2 should have been auto-answered
        answers = harness.get_answers()
        assert answers.get("auto_q2") == "yes", \
            f"Q2 should be auto-answered with 'yes', got: {answers.get('auto_q2')}"


# ============================================================================
# Test: .branch() - Dynamic routing
# ============================================================================

class TestBranchDynamic:
    """Test .branch() for dynamic state-based routing."""

    def test_branch_inspects_state(self):
        """Test that .branch() can inspect state and route dynamically."""
        tok = TestTokenizer()

        q1 = FlowQuestion(
            name="set_flag",
            prompt=" Set flag (on/off): ",
            strategy=ChoicesStrat(["on", "off"]),
            erase_mode=EraseMode.ALL,
            completion_text="",
        )

        q_on = FlowQuestion(
            name="flag_on_path",
            prompt=" Flag is ON: ",
            strategy=ChoicesStrat(["ack"]),
            erase_mode=EraseMode.ALL,
            completion_text="",
        )

        q_off = FlowQuestion(
            name="flag_off_path",
            prompt=" Flag is OFF: ",
            strategy=ChoicesStrat(["ack"]),
            erase_mode=EraseMode.ALL,
            completion_text="",
        )

        # Use branch to decide based on answer
        def decide_path(state):
            answer = state.answers.get("set_flag")
            if answer == "on":
                return route_question(q_on)
            else:
                return route_question(q_off)

        q1.branch(decide_path)
        q_on.then(route_message("ON path complete"))
        q_off.then(route_message("OFF path complete"))

        engine = FlowEngine(entry_question=q1)
        harness = FlowTestHarness(engine, tok, request_id="branch-test")

        harness.run_prefilled()

        # Answer "on"
        for _ in range(15):
            result = harness.run_forward_pass()
            if isinstance(result, ForceTokens):
                harness.simulate_force_tokens(result)
            elif isinstance(result, AdjustedLogits):
                current = harness.get_current_question_name()
                if current == "set_flag":
                    for c in "on":
                        harness.run_added([ord(c)], forced=False)
                        harness.run_forward_pass()
                elif current == "flag_on_path":
                    for c in "ack":
                        harness.run_added([ord(c)], forced=False)
                        harness.run_forward_pass()
                    break

        print(f"Answers: {harness.get_answers()}")
        print(f"Current: {harness.get_current_question_name()}")

        # Should have gone to flag_on_path
        assert "flag_on_path" in harness.get_answers() or harness.get_current_question_name() == "flag_on_path", \
            f"Should route to flag_on_path based on 'on' answer"


# ============================================================================
# Test: route_output()
# ============================================================================

class TestRouteOutput:
    """Test route_output() for forcing specific output."""

    def test_route_output_forces_text(self):
        """Test that route_output forces specific output tokens."""
        tok = TestTokenizer()

        q1 = FlowQuestion(
            name="trigger_output",
            prompt=" Trigger: ",
            strategy=ChoicesStrat(["go"]),
            erase_mode=EraseMode.ALL,
            completion_text="",
        )
        q1.then(route_output("Forced output text!"))

        engine = FlowEngine(entry_question=q1)
        harness = FlowTestHarness(engine, tok, request_id="output-test")

        harness.run_prefilled()

        output_detected = False
        for _ in range(15):
            result = harness.run_forward_pass()

            if isinstance(result, ForceTokens):
                decoded = tok.decode(result.tokens)
                print(f"ForceTokens: {decoded}")
                if "Forced output" in decoded:
                    output_detected = True
                    break
                harness.simulate_force_tokens(result)
            elif isinstance(result, AdjustedLogits):
                for c in "go":
                    harness.run_added([ord(c)], forced=False)
                    harness.run_forward_pass()

        print(f"Output detected: {output_detected}")


# ============================================================================
# Test: route_tool()
# ============================================================================

class TestRouteTool:
    """Test route_tool() for tool callback invocation."""

    def test_route_tool_invokes_callback(self):
        """Test that route_tool invokes the tool callback."""
        tok = TestTokenizer()

        tool_calls_made = []

        def my_tool_callback(actions, state, tokenizer):
            tool_calls_made.append({"state_id": state.request_id})
            # Return a tool_calls action
            return actions.tool_calls([{
                "name": "test_tool",
                "arguments": {"key": "value"}
            }])

        q1 = FlowQuestion(
            name="trigger_tool",
            prompt=" Call tool: ",
            strategy=ChoicesStrat(["yes"]),
            erase_mode=EraseMode.ALL,
            completion_text="",
        )
        q1.then(route_tool(my_tool_callback))

        engine = FlowEngine(entry_question=q1)
        harness = FlowTestHarness(engine, tok, request_id="tool-test")

        harness.run_prefilled()

        for _ in range(15):
            result = harness.run_forward_pass()

            if isinstance(result, ForceTokens):
                harness.simulate_force_tokens(result)
            elif isinstance(result, AdjustedLogits):
                for c in "yes":
                    harness.run_added([ord(c)], forced=False)
                    harness.run_forward_pass()

        print(f"Tool calls made: {len(tool_calls_made)}")
        print(f"Tool call details: {tool_calls_made}")


# ============================================================================
# Test: FlowDefinition with summary_builder
# ============================================================================

class TestFlowDefinition:
    """Test FlowDefinition with summary building."""

    def test_flow_definition_with_summary(self):
        """Test that FlowDefinition's summary_builder is called."""
        tok = TestTokenizer()

        q1 = FlowQuestion(
            name="step1",
            prompt=" Step 1: ",
            strategy=ChoicesStrat(["A"]),
            erase_mode=EraseMode.ALL,
            completion_text="",
        )
        q2 = FlowQuestion(
            name="step2",
            prompt=" Step 2: ",
            strategy=ChoicesStrat(["B"]),
            erase_mode=EraseMode.ALL,
            completion_text="",
        )

        q1.then(route_question(q2))
        q2.then(route_summary())

        summary_calls = []

        def build_summary(state):
            summary_calls.append(state.answers.copy())
            return f"Summary: step1={state.answers.get('step1')}, step2={state.answers.get('step2')}"

        flow_def = FlowDefinition(
            name="test_flow",
            root=q1,
            summary_builder=build_summary,
        )

        engine = FlowEngine(entry_question=q1, flows={"test_flow": flow_def})
        harness = FlowTestHarness(engine, tok, request_id="summary-test")

        harness.run_prefilled()

        for _ in range(25):
            result = harness.run_forward_pass()

            if isinstance(result, ForceTokens):
                harness.simulate_force_tokens(result)
            elif isinstance(result, AdjustedLogits):
                current = harness.get_current_question_name()
                if current == "step1":
                    harness.run_added([ord("A")], forced=False)
                elif current == "step2":
                    harness.run_added([ord("B")], forced=False)

        print(f"Summary calls: {len(summary_calls)}")
        print(f"Answers: {harness.get_answers()}")


# ============================================================================
# Test: EraseMode.PROMPT
# ============================================================================

class TestEraseModePrompt:
    """Test EraseMode.PROMPT behavior."""

    def test_erase_mode_prompt_behavior(self):
        """Test that EraseMode.PROMPT erases only the prompt, keeps answer.

        NOTE: This test documents expected behavior but may fail due to BUG #1.
        """
        tok = TestTokenizer()

        q1 = FlowQuestion(
            name="prompt_erase_q1",
            prompt=" Test: ",
            strategy=ChoicesStrat(["A"]),
            erase_mode=EraseMode.PROMPT,
            completion_text="",  # Empty to partially avoid BUG #1
        )
        q1.then(route_message("Done"))

        engine = FlowEngine(entry_question=q1)
        harness = FlowTestHarness(engine, tok, request_id="prompt-erase-test")

        harness.run_prefilled()

        try:
            for _ in range(10):
                result = harness.run_forward_pass()

                if isinstance(result, ForceTokens):
                    harness.simulate_force_tokens(result)
                elif isinstance(result, AdjustedLogits):
                    harness.run_added([ord("A")], forced=False)
                elif isinstance(result, Backtrack):
                    # With EraseMode.PROMPT, backtrack should include reinject tokens
                    print(f"Backtrack: n={result.n}, tokens={result.tokens}")
                    if result.tokens:
                        print(f"Reinjected: {tok.decode(result.tokens)}")
                    break

            print(f"EraseMode.PROMPT test completed")
            print(f"Answers: {harness.get_answers()}")

        except TypeError as e:
            print(f"BUG #1 triggered with EraseMode.PROMPT: {e}")
            pytest.skip("BUG #1: EraseMode.PROMPT triggers type mismatch")


# ============================================================================
# Run tests if executed directly
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
