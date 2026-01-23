"""Test adjust_logits action for ForwardPass event.

This test verifies that adjust_logits can modify the probability distribution.
Bans the em-dash token ("—") by setting its logit to -inf.
Expected: The model should never generate an em-dash token.
"""

from quote_mod_sdk import mod, ForwardPass
from max.driver import Tensor
import numpy as np

@mod
def test_forwardpass_adjust_logits(event, actions, tokenizer):
    """Bans the em-dash token by adjusting logits."""
    if isinstance(event, ForwardPass):
        # Get the logits as numpy array and make a copy
        logits = event.logits.to_numpy().copy()
        
        # Find the em-dash token ID
        em_dash_tokens = tokenizer.encode("—", add_special_tokens=False)
        if em_dash_tokens:
            em_dash_id = em_dash_tokens[0]
            
            # Ban it by setting logit to -inf
            logits[0,em_dash_id] = -np.inf
            
            # Return adjusted logits
            return actions.adjust_logits(Tensor.from_numpy(logits))
    
    return actions.noop()
