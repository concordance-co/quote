"""Test noop action for Prefilled event.

This test verifies that the noop action works correctly during the Prefilled event.
The mod receives the prefilled context but takes no action.
Expected: Normal generation continues unchanged.
"""

from quote_mod_sdk import mod, Prefilled

@mod
def test_prefilled_noop(event, actions, tokenizer):
    """Simply returns noop on Prefilled event."""
    if isinstance(event, Prefilled):
        # Do nothing, let generation proceed normally
        return actions.noop()
    
    return actions.noop()
