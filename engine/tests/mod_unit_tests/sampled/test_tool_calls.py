"""Test tool_calls action for Sampled event.

This test verifies that tool_calls can be triggered from the Sampled event.
After 2 tokens are sampled, triggers a database tool call.
Expected: Tool call is returned after 2 samples, interrupting generation.
"""

from quote_mod_sdk import mod, Sampled
from dataclasses import dataclass

@dataclass
class State:
    sample_count: int = 0
    tool_called: bool = False

states: dict[str, State] = {}

def get_state(rid: str) -> State:
    if rid not in states:
        states[rid] = State()
    return states[rid]

@mod
def test_sampled_tool_calls(event, actions, tokenizer):
    """Triggers a database tool call after 2 samples."""
    if isinstance(event, Sampled):
        st = get_state(event.request_id)
        st.sample_count += 1
        
        # After 2 samples, trigger tool call
        if st.sample_count == 2 and not st.tool_called:
            st.tool_called = True
            
            # Generate a safe call ID
            call_id = "call_test"
            if event.request_id:
                call_id = f"call_{event.request_id.split('-')[0]}"
            
            payload = {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": "query_database",
                    "arguments": "{\"table\": \"users\", \"limit\": 10}"
                }
            }
            return actions.tool_calls(payload)
    
    return actions.noop()
