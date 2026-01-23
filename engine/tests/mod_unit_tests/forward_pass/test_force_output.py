"""Test force_output action for ForwardPass event.

This test verifies that force_output immediately ends generation from forward pass.
After 3 tokens are generated, forces a specific ending and stops.
Expected: Generation stops after 3 tokens with the forced ending.
"""

from quote_mod_sdk import mod, ForwardPass, Added
from dataclasses import dataclass

@dataclass
class State:
    token_count: int = 0
    forced_output: bool = False

states: dict[str, State] = {}

def get_state(rid: str) -> State:
    if rid not in states:
        states[rid] = State()
    return states[rid]

@mod
def test_forwardpass_force_output(event, actions, tokenizer):
    """Forces output after 3 tokens have been generated."""
    st = get_state(event.request_id)
    
    if isinstance(event, Added):
        # Count non-forced tokens
        if not event.forced:
            st.token_count += len(event.added_tokens)
    
    if isinstance(event, ForwardPass):
        # After 3 tokens, force output and end
        if st.token_count >= 3 and not st.forced_output:
            st.forced_output = True
            ending = " [END]"
            ending_tokens = tokenizer.encode(ending, add_special_tokens=False)
            return actions.force_output(tokens=ending_tokens)
    
    return actions.noop()
