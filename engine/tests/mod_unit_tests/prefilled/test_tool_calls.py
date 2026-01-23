"""Test tool_calls action for Prefilled event.

This test verifies that tool_calls can be triggered from the Prefilled event.
If the prompt contains "weather", triggers a weather tool call immediately.
Expected: Tool call is returned instead of normal generation.
"""

from quote_mod_sdk import mod, Prefilled

@mod
def test_prefilled_tool_calls(event, actions, tokenizer):
    """Triggers a weather tool call when 'weather' is detected in prompt."""
    if isinstance(event, Prefilled):
        # Decode the prompt
        prompt_text = tokenizer.decode(
            event.context_info.tokens[:event.context_info._prompt_len]
        )
        
        # If 'weather' detected, trigger tool call
        if "weather" in prompt_text.lower():
            # Generate a safe call ID
            call_id = "call_test"
            if event.request_id:
                call_id = f"call_{event.request_id.split('-')[0]}"
            
            payload = {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": "{\"location\": \"New York\"}"
                }
            }
            return actions.tool_calls(payload)
    
    return actions.noop()
