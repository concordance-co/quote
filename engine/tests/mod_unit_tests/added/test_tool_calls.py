"""Test tool_calls action for Added event.

This test verifies that tool_calls can be triggered from the Added event.
When "search for" is detected in the output, triggers a search tool call.
Expected: Tool call is returned, interrupting normal generation.
"""

from quote_mod_sdk import mod, Added
from dataclasses import dataclass

@dataclass
class State:
    accumulated_text: str = ""
    tool_called: bool = False

states: dict[str, State] = {}

def get_state(rid: str) -> State:
    if rid not in states:
        states[rid] = State()
    return states[rid]

@mod
def test_added_tool_calls(event, actions, tokenizer):
    """Triggers a search tool call when 'search for' is detected."""
    if isinstance(event, Added):
        st = get_state(event.request_id)
        
        # Track non-forced tokens
        if not event.forced:
            text = tokenizer.decode(event.added_tokens)
            st.accumulated_text += text
            
            # If "search for" detected and we haven't called yet, trigger tool
            if "search for" in st.accumulated_text.lower() and not st.tool_called:
                st.tool_called = True
                
                # Generate a safe call ID
                call_id = "call_test"
                if event.request_id:
                    call_id = f"call_{event.request_id.split('-')[0]}"
                
                payload = {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": "search",
                        "arguments": "{\"query\": \"test query\"}"
                    }
                }
                return actions.tool_calls(payload)
    
    return actions.noop()
