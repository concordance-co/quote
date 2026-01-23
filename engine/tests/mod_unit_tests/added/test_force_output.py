"""Test force_output action for Added event.

This test verifies that force_output immediately ends generation from Added event.
When "stop word" is detected in the output, forces immediate ending.
Expected: Generation stops when "stop word" appears, with forced ending appended.
"""

from quote_mod_sdk import mod, Added
from dataclasses import dataclass

@dataclass
class State:
    accumulated_text: str = ""

states: dict[str, State] = {}

def get_state(rid: str) -> State:
    if rid not in states:
        states[rid] = State()
    return states[rid]

@mod
def test_added_force_output(event, actions, tokenizer):
    """Forces output and ends when 'stop word' is detected."""
    if isinstance(event, Added):
        st = get_state(event.request_id)
        
        # Track non-forced tokens
        if not event.forced:
            text = tokenizer.decode(event.added_tokens)
            st.accumulated_text += text
            
            # If "stop word" detected, force ending
            if "stop word" in st.accumulated_text.lower():
                ending = " [STOPPED]"
                ending_tokens = tokenizer.encode(ending, add_special_tokens=False)
                return actions.force_output(tokens=ending_tokens)
    
    return actions.noop()
