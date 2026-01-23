"""Test backtrack action for ForwardPass event.

This test verifies that backtrack works during forward pass.
Backtracks 2 steps after 5 tokens have been generated, then reinjects replacement text.
Expected: After 5 tokens, generation backtracks 2 steps and continues with new tokens.
"""

from quote_mod_sdk import mod, ForwardPass, Added
from dataclasses import dataclass

@dataclass
class State:
    token_count: int = 0
    backtracked: bool = False

states: dict[str, State] = {}

def get_state(rid: str) -> State:
    if rid not in states:
        states[rid] = State()
    return states[rid]

@mod
def test_forwardpass_backtrack(event, actions, tokenizer):
    """Backtracks 2 steps after 5 tokens, then reinjects new text."""
    st = get_state(event.request_id)
    
    if isinstance(event, Added):
        # Count non-forced tokens
        if not event.forced:
            st.token_count += len(event.added_tokens)
    
    if isinstance(event, ForwardPass):
        # After 5 tokens, backtrack 2 and reinject
        if st.token_count >= 5 and not st.backtracked:
            st.backtracked = True
            replacement_text = " [BACKTRACKED]"
            replacement_tokens = tokenizer.encode(replacement_text, add_special_tokens=False)
            return actions.backtrack(steps=1, tokens=replacement_tokens)
    
    return actions.noop()
