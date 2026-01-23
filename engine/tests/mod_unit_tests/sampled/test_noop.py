"""Test noop action for Sampled event.

This test verifies that the noop action works correctly during the Sampled event.
The mod observes sampled tokens but takes no action.
Expected: Normal generation continues unchanged.
"""

from quote_mod_sdk import mod, Sampled

@mod
def test_sampled_noop(event, actions, tokenizer):
    """Simply returns noop on Sampled event."""
    if isinstance(event, Sampled):
        # Observe the sampled token but do nothing
        return actions.noop()
    
    return actions.noop()
