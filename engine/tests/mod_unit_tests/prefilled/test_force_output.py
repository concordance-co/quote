"""Test force_output action for Prefilled event.

This test verifies that force_output immediately ends generation with specific tokens.
If the prompt contains "emergency", the mod forces a canned response and stops.
Expected: Generation is bypassed and only the forced output is returned.
"""

from quote_mod_sdk import mod, Prefilled

@mod
def test_prefilled_force_output(event, actions, tokenizer):
    """Forces a specific output when 'emergency' is detected in prompt."""
    if isinstance(event, Prefilled):
        # Decode the prompt
        prompt_text = tokenizer.decode(
            event.context_info.tokens[:event.context_info._prompt_len]
        )
        
        # If 'emergency' detected, force immediate output
        if "emergency" in prompt_text.lower():
            forced_response = "EMERGENCY PROTOCOL ACTIVATED. Please contact support immediately."
            forced_tokens = tokenizer.encode(forced_response, add_special_tokens=False)
            return actions.force_output(tokens=forced_tokens)
    
    return actions.noop()
