"""Test backtrack action for Added event.

This test verifies that backtrack works when triggered by Added event.
When "bad phrase" is detected, backtracks and replaces with "good phrase".
Expected: "bad phrase" is replaced with "good phrase" in the output.
"""

from quote_mod_sdk import mod, Added
from dataclasses import dataclass, field
from typing import List

@dataclass
class State:
    accumulated_text: str = ""
    accumulated_tokens: List[int] = field(default_factory=list)

states: dict[str, State] = {}

def get_state(rid: str) -> State:
    if rid not in states:
        states[rid] = State()
    return states[rid]

@mod
def test_added_backtrack(event, actions, tokenizer):
    """Backtracks when 'bad phrase' is detected and replaces with 'good phrase'."""
    if isinstance(event, Added):
        st = get_state(event.request_id)
        
        # Track non-forced tokens
        if not event.forced:
            text = tokenizer.decode(event.added_tokens)
            st.accumulated_text += text
            st.accumulated_tokens.extend(event.added_tokens)
            
            # Check if we just completed "bad phrase"
            if st.accumulated_text.endswith("bad phrase"):
                # Backtrack those tokens
                bad_tokens = tokenizer.encode("bad phrase", add_special_tokens=False)
                
                # Update our state
                st.accumulated_tokens = st.accumulated_tokens[:-len(bad_tokens)]
                st.accumulated_text = tokenizer.decode(st.accumulated_tokens)
                
                # Replace with good phrase
                good_text = "good phrase"
                good_tokens = tokenizer.encode(good_text, add_special_tokens=False)
                
                return actions.backtrack(steps=len(bad_tokens), tokens=good_tokens)
    
    return actions.noop()
