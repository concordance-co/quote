from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

from quote_mod_sdk.mod import mod
from quote_mod_sdk import ActionBuilder, Added, ForwardPass, Prefilled
from quote_mod_sdk.flow import FlowEngine

from .state import AppState
from .utils import handle_transfer, handle_update, populate_user_details, populate_reservation_details, populate_flight_status
from quote_mod_sdk import get_conversation
from examples.tau2.prompts import entry

# Engine wiring
# Engine wiring with all flows
ENGINE = FlowEngine(
    entry_question=entry,
    state_factory=lambda rid: AppState(request_id=rid),
)

@mod
def airline_helper_v3(event, actions: ActionBuilder, tokenizer: Any):
    request_id = getattr(event, "request_id", None)

    had_state = False
    if isinstance(event, Prefilled):
        logger.debug("conversation: %s", get_conversation())
    if request_id:
        had_state = ENGINE._states.get(request_id) is not None
        state = ENGINE._get_state(request_id)
        failed, no_new_messages = populate_user_details(state)
        if failed and no_new_messages:
            state_hint = None
            source = get_conversation()
            extra = ""
            if source:
                if len(source) >= 2:
                    if source[-2].get("tool_calls"):
                        if source[-1]["role"] == "tool":
                            hint = source[-1]["tool_call_id"].split(".")
                            state_hint = hint[1] if 1 < len(hint) else None
            if state_hint == "RES_INFO":
                extra = "While trying to find your reservation information, "
            elif state_hint == "CANCEL":
                extra = "While trying to cancel your reservation, "
            elif state_hint == "MODIFY":
                extra = "While trying to modify your reservation, "
            elif state_hint == "BOOK":
                extra = "While trying to book a new reservation, "
            return actions.force_output(tokenizer.encode(f"{extra}I tried to get your user details but failed. Could you provide your user id?", add_special_tokens=False))
        populate_reservation_details(state)
        populate_flight_status(state)
        if handle_transfer():
            toks = tokenizer.encode("YOU ARE BEING TRANSFERRED TO A HUMAN AGENT. PLEASE HOLD ON.", add_special_tokens=False)
            return actions.force_output(toks)
        (was_updated, info) = handle_update()
        if was_updated:
            import json
            toks = tokenizer.encode(f"I have updated your reservation: {json.dumps(info)}. Is there anything else I can help you with?", add_special_tokens=False)
            return actions.force_output(toks)
    if isinstance(event, Prefilled) and not had_state:
        # import re
        return ENGINE.handle_event(event, actions, tokenizer)

        # return actions.adjust_prefill(tokens=tokenizer.encode(text, add_special_tokens=False))
    if isinstance(event, (ForwardPass, Added)):
        return ENGINE.handle_event(event, actions, tokenizer)
    return actions.noop()
