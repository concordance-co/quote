from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = PROJECT_ROOT / "src"
INFER_PATH = PROJECT_ROOT / "inference" / "src"
SHARED_PATH = PROJECT_ROOT / "shared" / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
if str(INFER_PATH) not in sys.path:
    sys.path.insert(0, str(INFER_PATH))
if str(SHARED_PATH) not in sys.path:
    sys.path.insert(0, str(SHARED_PATH))

import pytest

from sdk.quote_mod_sdk.actions import ActionBuilder
from shared.types import (
    Prefilled as PrefilledEvent,
    ForwardPass as ForwardPassEvent,
    Added as AddedEvent,
    ForceTokens,
    AdjustedLogits,
    Backtrack,
)
from sdk.quote_mod_sdk.self_prompt import SelfPrompt, EraseMode
from sdk.quote_mod_sdk.strategies.strategy_constructor import ChoicesStrat, ListStrat
from tests.sdk.utils import TestTokenizer, DummyLogits


def _build_events(rid: str = "req-1", step: int = 0, tokens_len: int = 0):
    # Minimal tensor-like logits, fresh per step
    logits = DummyLogits(256)
    pre = PrefilledEvent(request_id=rid, step=step, max_steps=8, context_info={})
    fwd = ForwardPassEvent(request_id=rid, step=step + 1, logits=logits)
    return pre, fwd


def test_self_prompt_forces_prompt_and_masks_allowed():
    tok = TestTokenizer()
    sp = SelfPrompt(
        prompt={"text": "Q:"},
        strategy=ChoicesStrat(["A", "B"]),
        completion=None,
        erase=EraseMode.NONE,
    )
    pre, fwd = _build_events(step=0, tokens_len=0)
    actions = ActionBuilder(fwd)

    # Prefill compiles state
    sp.handle_prefilled(pre, tok)

    # First forward pass should force prompt tokens
    a1 = sp.handle_forward_pass(fwd, actions, tok)
    assert isinstance(a1, ForceTokens)
    assert [chr(t) for t in a1.tokens] == list("Q:")

    # Simulate prompt being added as forced
    add = AddedEvent(request_id=pre.request_id, step=2, added_tokens=[ord("Q"), ord(":")], forced=True)
    sp.handle_added(add, actions, tok)

    # Next cycle: Prefill -> Forward -> Added (sample one of the allowed choices for completeness)
    pre2, fwd2 = _build_events(rid=pre.request_id, step=3, tokens_len=2)
    sp.handle_prefilled(pre2, tok)
    a2 = sp.handle_forward_pass(fwd2, ActionBuilder(fwd2), tok)
    assert isinstance(a2, AdjustedLogits)
    sp.handle_added(AddedEvent(pre.request_id, 4, [ord("A")], False), ActionBuilder(fwd2), tok)
    # No specific assertion after add; ensure no exceptions


@pytest.mark.parametrize("with_completion", [False, True])
def test_self_prompt_erase_modes_prompt_and_all(with_completion: bool):
    tok = TestTokenizer()
    suffix_cfg = "\n" if with_completion else None

    # PROMPT erase: reinject the answer only
    sp_prompt = SelfPrompt(
        prompt={"text": "Q:"},
        strategy=ChoicesStrat(["Y"]),
        completion=suffix_cfg,
        erase=EraseMode.PROMPT,
    )
    pre, fwd = _build_events("req-3")
    actions = ActionBuilder(fwd)
    sp_prompt.handle_prefilled(pre, tok)
    # Cycle 1: Forward -> Added prompt
    _ = sp_prompt.handle_forward_pass(fwd, actions, tok)
    sp_prompt.handle_added(AddedEvent(pre.request_id, 1, [ord("Q"), ord(":")], True), actions, tok)
    # Cycle 2: Prefill -> Forward -> Added answer
    pre_a, fwd_a = _build_events("req-3", step=2, tokens_len=2)
    sp_prompt.handle_prefilled(pre_a, tok)
    _ = sp_prompt.handle_forward_pass(fwd_a, ActionBuilder(fwd_a), tok)
    sp_prompt.handle_added(AddedEvent(pre.request_id, 2, [ord("Y")], False), ActionBuilder(fwd_a), tok)

    # Cycle 3: Prefill -> Forward (depends on completion)
    pre_b, fwd_b = _build_events("req-3", step=3, tokens_len=3)
    sp_prompt.handle_prefilled(pre_b, tok)
    res = sp_prompt.handle_forward_pass(fwd_b, ActionBuilder(fwd_b), tok)
    if with_completion:
        # Expect forcing suffix first
        assert isinstance(res, ForceTokens)
        # Simulate suffix being added as forced (Cycle 3 Added)
        sp_prompt.handle_added(
            AddedEvent(pre.request_id, 3, [ord("\n")], True), ActionBuilder(fwd_b), tok
        )
        # Cycle 4: Prefill -> Forward should backtrack prompt+answer+suffix
        pre_c, fwd_c = _build_events("req-3", step=4, tokens_len=4)
        sp_prompt.handle_prefilled(pre_c, tok)
        res = sp_prompt.handle_forward_pass(fwd_c, ActionBuilder(fwd_c), tok)
        assert isinstance(res, Backtrack)
        assert res.n == 4  # Q : Y and suffix '\n'
    else:
        # No completion => immediate backtrack of prompt+answer in Cycle 3
        assert isinstance(res, Backtrack)
        assert res.n == 3
    # Reinjected should be the answer only in PROMPT erase
    assert [chr(t) for t in (res.tokens or [])] == ["Y"]

    # ALL erase: no reinjection
    sp_all = SelfPrompt(
        prompt={"text": "P"},
        strategy=ChoicesStrat(["Z"]),
        completion=suffix_cfg,
        erase=EraseMode.ALL,
    )
    pre2, fwd2 = _build_events("req-4")
    actions2 = ActionBuilder(fwd2)
    sp_all.handle_prefilled(pre2, tok)
    # Cycle 1: Forward -> Added prompt
    _ = sp_all.handle_forward_pass(fwd2, actions2, tok)
    sp_all.handle_added(AddedEvent(pre2.request_id, 1, [ord("P")], True), actions2, tok)
    # Cycle 2: Prefill -> Forward -> Added answer
    pre2_a, fwd2_a = _build_events("req-4", step=2, tokens_len=1)
    sp_all.handle_prefilled(pre2_a, tok)
    _ = sp_all.handle_forward_pass(fwd2_a, ActionBuilder(fwd2_a), tok)
    sp_all.handle_added(AddedEvent(pre2.request_id, 2, [ord("Z")], False), ActionBuilder(fwd2_a), tok)
    # Cycle 3: Prefill -> Forward (maybe suffix) / Added
    pre2_b, fwd2_b = _build_events("req-4", step=3, tokens_len=2)
    sp_all.handle_prefilled(pre2_b, tok)
    res2 = sp_all.handle_forward_pass(fwd2_b, ActionBuilder(fwd2_b), tok)
    assert isinstance(res2, Backtrack)
    print(res2.__dict__)
    # n counts prompt + answer -> we dont emit a completion token when backtrack == ALL
    assert res2.n == 2
    assert res2.tokens is None


def test_refresh_responses_updates_choices():
    tok = TestTokenizer()
    # List of choices as single element
    spec = ListStrat([ChoicesStrat(["cat", "dog"])])
    sp = SelfPrompt(strategy=spec)
    pre, fwd = _build_events("req-5")
    actions = ActionBuilder(fwd)
    sp.handle_prefilled(pre, tok)
    a1 = sp.handle_forward_pass(fwd, actions, tok)
    assert isinstance(a1, AdjustedLogits)

    # Update choices for element 0
    sp.refresh_responses(["owl"], request_id=pre.request_id, idx=0)
    # Should recompile and now allow only 'o' as starting choice
    a2 = sp.handle_forward_pass(fwd, actions, tok)
    assert isinstance(a2, AdjustedLogits)
