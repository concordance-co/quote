"""Test noop action for Added event.

This test verifies that the noop action works correctly during the Added event.
The mod observes added tokens but takes no action.
Expected: Normal generation continues unchanged.
"""

from quote_mod_sdk import mod, Added

@mod
def test_added_noop(event, actions, tokenizer):
    """Simply returns noop on Added event."""
    if isinstance(event, Added):
        # Observe the token but do nothing
        return actions.noop()
    
    return actions.noop()
