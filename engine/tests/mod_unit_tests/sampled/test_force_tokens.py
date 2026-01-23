"""Test force_tokens action for Sampled event.

This test verifies that force_tokens can inject tokens after observing sampled token.
When any token is sampled, forces " [OBSERVED]" once.
Expected: First sampled token is followed by " [OBSERVED]".
"""

from quote_mod_sdk import mod, Sampled
from dataclasses import dataclass

@dataclass
class State:
    observed_once: bool = False

states: dict[str, State] = {}

def get_state(rid: str) -> State:
    if rid not in states:
        states[rid] = State()
    return states[rid]

@mod
def test_sampled_force_tokens(event, actions, tokenizer):
    """Forces ' [OBSERVED]' after first sampled token."""
    if isinstance(event, Sampled):
        st = get_state(event.request_id)
        
        # Force tokens once after observing first sample
        if not st.observed_once:
            st.observed_once = True
            forced_text = " [OBSERVED]"
            forced_tokens = tokenizer.encode(forced_text, add_special_tokens=False)
            return actions.force_tokens(tokens=forced_tokens)
    
    return actions.noop()
