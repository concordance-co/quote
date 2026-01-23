"""Test noop action for ForwardPass event.

This test verifies that the noop action works correctly during the ForwardPass event.
The mod receives logits but takes no action.
Expected: Normal sampling continues unchanged.
"""

from quote_mod_sdk import mod, ForwardPass

@mod
def test_forwardpass_noop(event, actions, tokenizer):
    """Simply returns noop on ForwardPass event."""
    if isinstance(event, ForwardPass):
        # Do nothing, let sampling proceed normally
        return actions.noop()
    
    return actions.noop()
