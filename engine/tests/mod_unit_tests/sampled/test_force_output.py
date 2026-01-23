"""Test force_output action for Sampled event.

This test verifies that force_output immediately ends generation from Sampled event.
After 5 tokens are sampled, forces ending and stops generation.
Expected: Generation stops after 5 sampled tokens with forced ending.
"""

from quote_mod_sdk import mod, Sampled
from dataclasses import dataclass

@dataclass
class State:
    sample_count: int = 0

states: dict[str, State] = {}

def get_state(rid: str) -> State:
    if rid not in states:
        states[rid] = State()
    return states[rid]

@mod
def test_sampled_force_output(event, actions, tokenizer):
    """Forces output after 5 sampled tokens."""
    if isinstance(event, Sampled):
        st = get_state(event.request_id)
        st.sample_count += 1
        
        # After 5 samples, force ending
        if st.sample_count == 5:
            ending = " [SAMPLED_END]"
            ending_tokens = tokenizer.encode(ending, add_special_tokens=False)
            return actions.force_output(tokens=ending_tokens)
    
    return actions.noop()
