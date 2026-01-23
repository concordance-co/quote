"""Test force_tokens action for Added event.

This test verifies that force_tokens can inject tokens after observing added tokens.
When the accumulated text contains "hello", forces " world" to follow.
Expected: "hello" is always followed by " world".
"""

from quote_mod_sdk import mod, Added
from dataclasses import dataclass, field

@dataclass
class State:
    accumulated_text: str = ""
    forced_world: bool = False

states: dict[str, State] = {}

def get_state(rid: str) -> State:
    if rid not in states:
        states[rid] = State()
    return states[rid]

@mod
def test_added_force_tokens(event, actions, tokenizer):
    """Forces ' world' after detecting 'hello'."""
    if isinstance(event, Added):
        st = get_state(event.request_id)
        
        # Track non-forced tokens
        if not event.forced:
            text = tokenizer.decode(event.added_tokens)
            st.accumulated_text += text
            
            # If we just completed "hello", force " world"
            if "hello" in st.accumulated_text.lower() and not st.forced_world:
                st.forced_world = True
                forced_text = " world"
                forced_tokens = tokenizer.encode(forced_text, add_special_tokens=False)
                return actions.force_tokens(tokens=forced_tokens)
    
    return actions.noop()
