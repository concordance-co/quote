from __future__ import annotations

import pytest

from sdk.quote_mod_sdk.strategies.strategy_constructor import (
    ChoicesStrat,
    UntilStrat,
    ListStrat,
    CharsStrat,
)
from sdk.quote_mod_sdk.strategies.primitives import UntilEndType, CharsMode
from tests.sdk.utils import TestTokenizer


def test_choices_strategy_basic_completion():
    tok = TestTokenizer()
    strat = ChoicesStrat(["hi", "hit"]).into_strategy(tok)
    st = strat.start(tok)
    allowed = strat.allowed_tokens(st, tok)
    assert chr(next(iter(allowed))) == "h"
    # Step 'h'
    strat.step(st, ord("h"), tok)
    allowed = strat.allowed_tokens(st, tok)
    assert allowed == {ord("i")}
    # Step 'i' completes choice 'hi' (no outgoing edges needed)
    strat.step(st, ord("i"), tok)
    assert strat.is_complete(st) is True


def test_until_strategy_tag_and_anychar():
    tok = TestTokenizer()

    # TAG-based: force start tag then run until stop tag appears
    u_tag = UntilStrat("<a>", UntilEndType.TAG, "</a>").into_strategy(tok)
    st = u_tag.start(tok)
    allowed = u_tag.allowed_tokens(st, tok)
    assert allowed == {ord("<")}
    # Emit '<a>'
    for ch in "<a>":
        u_tag.step(st, ord(ch), tok)
    # Now any token allowed; emit some content then the stop sequence
    for ch in "xyz</a>":
        u_tag.step(st, ord(ch), tok)
    assert u_tag.is_complete(st) is True

    # ANYCHAR-based: completes when any of the stop chars is seen
    u_any = UntilStrat("", UntilEndType.ANYCHAR, "\n.").into_strategy(tok)
    st2 = u_any.start(tok)
    # All tokens are allowed initially since no start tag
    assert len(u_any.allowed_tokens(st2, tok)) > 0
    # Emit regular chars then a stop char '.'
    for ch in "hello.":
        u_any.step(st2, ord(ch), tok)
    assert u_any.is_complete(st2) is True


def test_chars_strategy_modes_and_limits():
    tok = TestTokenizer()

    # Alpha until '.' with min 1
    cs = CharsStrat(CharsMode.ALPHA, stop=".", min=1).into_strategy(tok)
    st = cs.start(tok)
    allowed = cs.allowed_tokens(st, tok)
    assert ord("a") in allowed and ord("1") not in allowed
    cs.step(st, ord("a"), tok)
    # After min satisfied, stop token is permitted
    allowed = cs.allowed_tokens(st, tok)
    assert ord(".") in allowed
    cs.step(st, ord("."), tok)
    assert cs.is_complete(st) is True

    # Numeric fixed length 3
    cs2 = CharsStrat(CharsMode.NUMERIC, stop=3).into_strategy(tok)
    st2 = cs2.start(tok)
    for ch in "123":
        allowed = cs2.allowed_tokens(st2, tok)
        assert ord(ch) in allowed
        cs2.step(st2, ord(ch), tok)
    assert cs2.is_complete(st2) is True


def test_list_strategy_with_wrap_sep_and_end_with():
    tok = TestTokenizer()
    # One element list of up to 1 alphanumeric char wrapped in quotes, closed by ']', and end with '.'
    elem = CharsStrat(CharsMode.ALPHANUMERIC, stop=1)
    ls = ListStrat(
        elements=elem,
        open="[",
        close="]",
        wrap="\"",
        sep=", ",
        min=1,
        max=1,
        end_with=".",
    ).into_strategy(tok)
    st = ls.start(tok)

    # Open list
    allowed = ls.allowed_tokens(st, tok)
    assert allowed == {ord("[")}
    ls.step(st, ord("["), tok)

    # Wrap open -> directly enters element (single char wrap)
    allowed = ls.allowed_tokens(st, tok)
    assert allowed == {ord("\"")}
    ls.step(st, ord("\""), tok)

    # In element: one alphanumeric character allowed
    allowed = ls.allowed_tokens(st, tok)
    assert ord("a") in allowed
    ls.step(st, ord("a"), tok)

    # Close wrap
    allowed = ls.allowed_tokens(st, tok)
    assert allowed == {ord("\"")}
    ls.step(st, ord("\""), tok)

    # After element: min satisfied so close list is allowed
    allowed = ls.allowed_tokens(st, tok)
    assert ord("]") in allowed
    ls.step(st, ord("]"), tok)

    # end_with '.' must be consumed to complete
    allowed = ls.allowed_tokens(st, tok)
    assert allowed == {ord(".")}
    ls.step(st, ord("."), tok)
    assert ls.is_complete(st) is True


def test_list_fixed_elements_with_multitoken_wrap_and_end_with():
    tok = TestTokenizer()

    # Two fixed elements: "ab" and "cd"; list has multi-token wrap and end_with suffix
    ls = ListStrat(
        elements=[ChoicesStrat(["ab"]), ChoicesStrat(["cd"])],
        open="[",
        close="]",
        wrap='""',  # two-token wrap
        sep=", ",
        end_with="OK",
    ).into_strategy(tok)

    st = ls.start(tok)

    # Open list '['
    assert ls.allowed_tokens(st, tok) == {ord('[')}
    ls.step(st, ord('['), tok)

    # Wrap open requires two quotes
    assert ls.allowed_tokens(st, tok) == {ord('"')}
    ls.step(st, ord('"'), tok)
    assert ls.allowed_tokens(st, tok) == {ord('"')}
    ls.step(st, ord('"'), tok)

    # First element: "ab"
    allowed = ls.allowed_tokens(st, tok)
    assert ord('a') in allowed
    ls.step(st, ord('a'), tok)
    allowed = ls.allowed_tokens(st, tok)
    assert ord('b') in allowed
    ls.step(st, ord('b'), tok)

    # Close wrap for first element
    assert ls.allowed_tokens(st, tok) == {ord('"')}
    ls.step(st, ord('"'), tok)
    assert ls.allowed_tokens(st, tok) == {ord('"')}
    ls.step(st, ord('"'), tok)

    # Must add a separator, since two elements required
    assert ls.allowed_tokens(st, tok) == {ord(',')}
    ls.step(st, ord(','), tok)
    assert ls.allowed_tokens(st, tok) == {ord(' ')}
    ls.step(st, ord(' '), tok)

    # Second element, wrapped
    assert ls.allowed_tokens(st, tok) == {ord('"')}
    ls.step(st, ord('"'), tok)
    assert ls.allowed_tokens(st, tok) == {ord('"')}
    ls.step(st, ord('"'), tok)
    allowed = ls.allowed_tokens(st, tok)
    assert ord('c') in allowed
    ls.step(st, ord('c'), tok)
    allowed = ls.allowed_tokens(st, tok)
    assert ord('d') in allowed
    ls.step(st, ord('d'), tok)
    # Close wrap
    assert ls.allowed_tokens(st, tok) == {ord('"')}
    ls.step(st, ord('"'), tok)
    assert ls.allowed_tokens(st, tok) == {ord('"')}
    ls.step(st, ord('"'), tok)

    # Now close the list
    assert ls.allowed_tokens(st, tok) == {ord(']')}
    ls.step(st, ord(']'), tok)

    # end_with "OK"
    assert ls.allowed_tokens(st, tok) == {ord('O')}
    ls.step(st, ord('O'), tok)
    assert ls.allowed_tokens(st, tok) == {ord('K')}
    ls.step(st, ord('K'), tok)

    assert ls.is_complete(st) is True


def test_list_with_multitoken_open_close_and_single_char_elements():
    tok = TestTokenizer()

    # Two single-character elements, list with multi-token open/close
    ls = ListStrat(
        elements=[ChoicesStrat(["x"]), ChoicesStrat(["y"])],
        open="<<",
        close=">",
        wrap='"',
        sep=", ",
        end_with=".",
    ).into_strategy(tok)

    st = ls.start(tok)

    # Multi-token open
    assert ls.allowed_tokens(st, tok) == {ord('<')}
    ls.step(st, ord('<'), tok)
    assert ls.allowed_tokens(st, tok) == {ord('<')}
    ls.step(st, ord('<'), tok)

    # First element: wrapped
    assert ls.allowed_tokens(st, tok) == {ord('"')}
    ls.step(st, ord('"'), tok)
    allowed = ls.allowed_tokens(st, tok)
    assert ord('x') in allowed
    ls.step(st, ord('x'), tok)
    # Wrap close
    assert ls.allowed_tokens(st, tok) == {ord('"')}
    ls.step(st, ord('"'), tok)

    # Separator (two tokens: ", ")
    assert ls.allowed_tokens(st, tok) == {ord(',')}
    ls.step(st, ord(','), tok)
    assert ls.allowed_tokens(st, tok) == {ord(' ')}
    ls.step(st, ord(' '), tok)

    # Second element
    assert ls.allowed_tokens(st, tok) == {ord('"')}
    ls.step(st, ord('"'), tok)
    allowed = ls.allowed_tokens(st, tok)
    assert ord('y') in allowed
    ls.step(st, ord('y'), tok)
    assert ls.allowed_tokens(st, tok) == {ord('"')}
    ls.step(st, ord('"'), tok)

    # Close list (single-token close '>') then end_with '.'
    assert ls.allowed_tokens(st, tok) == {ord('>')}
    ls.step(st, ord('>'), tok)
    assert ls.allowed_tokens(st, tok) == {ord('.')}
    ls.step(st, ord('.'), tok)
    assert ls.is_complete(st) is True
