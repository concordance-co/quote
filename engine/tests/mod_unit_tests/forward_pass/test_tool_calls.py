"""Test tool_calls action for ForwardPass event.

This test verifies that tool_calls can be triggered from the ForwardPass event.
After the model starts generating (first forward pass), triggers a calculator tool call.
Expected: Tool call is returned, interrupting normal generation.
"""

from quote_mod_sdk import mod, ForwardPass
from dataclasses import dataclass

@dataclass
class State:
    tool_called: bool = False

states: dict[str, State] = {}

def get_state(rid: str) -> State:
    if rid not in states:
        states[rid] = State()
    return states[rid]

@mod
def test_forwardpass_tool_calls(event, actions, tokenizer):
    """Triggers a tool call on the first forward pass."""
    if isinstance(event, ForwardPass):
        st = get_state(event.request_id)
        
        # Trigger tool call once
        if not st.tool_called:
            st.tool_called = True
            
            # Generate a safe call ID
            call_id = "call_test"
            if event.request_id:
                call_id = f"call_{event.request_id.split('-')[0]}"
            
            payload = {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": "calculator",
                    "arguments": "{\"operation\": \"add\", \"a\": 2, \"b\": 2}"
                }
            }
            return actions.tool_calls(payload)
    
    return actions.noop()
