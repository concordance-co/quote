"""Test backtrack action for Sampled event.

This test verifies that backtrack works when triggered by Sampled event.
After 3 tokens are sampled, backtracks 1 step and reinjects alternative.
Expected: After 3 tokens, one is removed and replaced.
"""

from quote_mod_sdk import mod, Sampled, ActionBuilder
from dataclasses import dataclass

@dataclass
class State:
    sample_count: int = 0
    backtracked: bool = False

states: dict[str, State] = {}

def get_state(rid: str) -> State:
    if rid not in states:
        states[rid] = State()
    return states[rid]

@mod
def test_sampled_backtrack(event, actions: ActionBuilder, tokenizer):
    """Backtracks 1 step after 3 samples and reinjects alternative."""
    if isinstance(event, Sampled):
        st = get_state(event.request_id)
        st.sample_count += 1

        # After 3 samples, backtrack 1
        if st.sample_count == 3 and not st.backtracked:
            st.backtracked = True
            alternative = " [RESAMPLED]"
            alternative_tokens = tokenizer.encode(alternative, add_special_tokens=False)
            return actions.backtrack(steps=1, tokens=alternative_tokens)
        

    return actions.noop()
