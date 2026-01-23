"""Test force_tokens action for ForwardPass event.

This test verifies that force_tokens can inject specific tokens during the forward pass.
Forces " [INJECTED]" as the first token of generation.
Expected: The output starts with " [INJECTED]" followed by normal generation.
"""

from quote_mod_sdk import mod, ForwardPass
from dataclasses import dataclass

@dataclass
class State:
    injected: bool = False

states: dict[str, State] = {}

def get_state(rid: str) -> State:
    if rid not in states:
        states[rid] = State()
    return states[rid]

@mod
def test_forwardpass_force_tokens(event, actions, tokenizer):
    """Forces specific tokens on the first forward pass."""
    if isinstance(event, ForwardPass):
        st = get_state(event.request_id)
        
        # Only inject once at the start
        if not st.injected:
            st.injected = True
            forced_text = " [INJECTED]"
            forced_tokens = tokenizer.encode(forced_text, add_special_tokens=False)
            return actions.force_tokens(tokens=forced_tokens)
    
    return actions.noop()
