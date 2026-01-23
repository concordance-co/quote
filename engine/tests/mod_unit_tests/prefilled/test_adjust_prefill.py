"""Test adjust_prefill action for Prefilled event.

This test verifies that adjust_prefill can modify the input prompt before generation.
The mod replaces "hello" with "goodbye" in the prompt.
Expected: If prompt contains "hello", it should be replaced with "goodbye".
"""

from quote_mod_sdk import mod, Prefilled

@mod
def test_prefilled_adjust_prefill(event, actions, tokenizer):
    """Replaces 'hello' with 'goodbye' in the prompt."""
    if isinstance(event, Prefilled):
        # Decode the prompt
        prompt_text = tokenizer.decode(
            event.context_info.tokens[:event.context_info._prompt_len]
        )
        
        # Replace 'hello' with 'goodbye'
        if "hello" in prompt_text.lower():
            new_prompt = prompt_text.replace("hello", "goodbye").replace("Hello", "Goodbye")
            new_tokens = tokenizer.encode(new_prompt, add_special_tokens=False)
            return actions.adjust_prefill(tokens=new_tokens)
    
    return actions.noop()
