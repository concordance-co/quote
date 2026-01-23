import json
from typing import Tuple, Any, List, Dict, Optional
from quote_mod_sdk import get_conversation, tool_call_pairs
from quote_mod_sdk.flow import route_tool

from .state import UserDetailsRecord, ReservationDetailsRecord, AppState




def call_search_flight(actions, ctx: AppState, tokenizer: Any):
    if ctx.answers.get("planner.extract_trip_origin"):
        orig = ctx.answers["planner.extract_trip_origin"]
    else:
        return actions.force_output("I'll need the trip origin airport code please.")
    if ctx.answers.get("planner.extract_trip_destination"):
        dest = ctx.answers["planner.extract_trip_destination"]
    else:
        return actions.force_output("I'll need the trip destination airport code please.")
    if ctx.answers.get("planner.extract_date_of_trip"):
        date = ctx.answers["planner.extract_date_of_trip"]
    else:
        return actions.force_output("I'll need the trip date please.")
    payload = {
        "id": f"call_{ctx.request_id.split('-')[0]}" + f"{ctx.state_hint}" if ctx.state_hint else "",
        "type": "function",
        "function": {"name": "search_direct_flight", "arguments": json.dumps({"origin": orig, "destination": dest, "date": date})},
    }
    return actions.tool_calls(payload)


def call_list_all_airports(actions, ctx: AppState, tokenizer: Any):
    payload = {
        "id": f"call_{ctx.request_id.split('-')[0]}" + f"{ctx.state_hint}" if ctx.state_hint else "",
        "type": "function",
        "function": {"name": "list_all_airports", "arguments": ""},
    }
    return actions.tool_calls(payload)

def call_transfer_to_humans(actions, ctx: AppState, tokenizer: Any):
    summary = (
        f"User ID: {ctx.user_details.user_id or '-'}; Reservation: {ctx.active_reservation.reservation_id or '-'}; Reason: {ctx.transfer_reason or '-'}"
    )
    payload = {
        "id": f"call_{ctx.request_id.split('-')[0]}",
        "type": "function",
        "function": {"name": "transfer_to_human_agents", "arguments": json.dumps({"summary": summary})},
    }
    return actions.tool_calls(payload)


def transfer_flow(ctx: AppState, reason: str):
    ctx.transfer_reason = reason
    return route_tool(call_transfer_to_humans)

def call_get_flight_status(actions, state: AppState, tokenizer: Any):
    import json
    if not state.active_reservation.reservation_id:
        return force_message(actions, tokenizer, "Hmm something went wrong. Let me transfer you to a human agent.")

    if state.answers.get("planner.extract_flight_number_to_get_information_on") and state.answers.get("planner.extract_flight_number_date_to_get_information_on"):
        payload = {
            "id": f"call_{state.request_id.split('-')[0]}" + f"{state.state_hint}" if state.state_hint else "",
            "type": "function",
            "function": {"name": "get_flight_status", "arguments": json.dumps({
                "flight_number": state.answers["planner.extract_flight_number_to_get_information_on"],
                "date": state.answers["planner.extract_flight_number_date_to_get_information_on"]
            })}
        }
        return actions.tool_calls(payload)
    else:
        details = state.reservations[state.active_reservation.reservation_id]
        if not details.flights:
            return force_message(actions, tokenizer, "I couldn't find any flights under that reservation.")
        flight_number = details.flights[0].get("flight_number")
        flight_date = details.flights[0].get("date")
        if not flight_number or not flight_date:
            return force_message(actions, tokenizer, "I couldn't find any flights under that reservation.")
        payload = {
            "id": f"call_{state.request_id.split('-')[0]}" + f"{state.state_hint}" if state.state_hint else "",
            "type": "function",
            "function": {"name": "get_flight_status", "arguments": json.dumps({"flight_number": flight_number, "date": flight_date})},
        }
        return actions.tool_calls(payload)

def call_cancel_reservation(actions, state: AppState, tokenizer: Any):
    if not state.active_reservation.reservation_id:
        return transfer_flow(state, "Something went wrong cancelling a reservation")
    payload = {
        "id": f"call_{state.request_id.split('-')[0]}",
        "type": "function",
        "function": {"name": "cancel_reservation", "arguments": json.dumps({"reservation_id": state.active_reservation.reservation_id})},
    }
    return actions.tool_calls(payload)

def call_update_reservation_flights(actions, state: AppState, tokenizer: Any):
    if not state.active_reservation.reservation_id:
        return actions.force_output("I'll need your reservation id to modify it.")
    if not state.active_reservation.cabin:
        return actions.force_output("I'll need your desired cabin type to modify this reservation.")
    if not state.active_reservation.flights:
        return actions.force_output("I'll need your flight segments to modify this reservation.")
    if not state.active_reservation.payment_method:
        return actions.force_output("I'll need your desired payment method to modify this reservation.")
    payload = {
        "id": f"call_{state.request_id.split('-')[0]}",
        "type": "function",
        "function": {"name": "update_reservation_flights", "arguments": json.dumps({
            "reservation_id": state.active_reservation.reservation_id,
            "cabin": state.active_reservation.cabin,
            "flights": state.active_reservation.flights,
            "payment_id": state.active_reservation.payment_method,
        })},
    }
    return actions.tool_calls(payload)

def call_book_flight_reservation(actions, state: AppState, tokenizer: Any):
    import json
    if state.answers.get("planner.extract_user_id") and not state.user_id:
        state.user_id = state.answers["planner.extract_user_id"]
    if state.answers.get("planner.extract_trip_origin"):
        state.active_reservation.origin = state.answers["planner.extract_trip_origin"]
    if state.answers.get("planner.extract_trip_destination"):
        state.active_reservation.destination = state.answers["planner.extract_trip_destination"]
    if state.answers.get("planner.extract_passengers"):
        state.active_reservation.passengers = json.loads(state.answers["planner.extract_passengers"])
    if state.answers.get("planner.extract_flight_type"):
        state.active_reservation.flight_type = state.answers["planner.extract_flight_type"]
    if state.answers.get("planner.extract_cabin"):
        state.active_reservation.cabin = state.answers["planner.extract_cabin"]
    if state.answers.get("planner.extract_payment_id"):
        state.active_reservation.payment_method = state.answers["planner.extract_payment_id"]
    if state.answers.get("planner.extract_number_of_additional_bags"):
        state.active_reservation.total_baggages = int(state.answers["planner.extract_number_of_additional_bags"].strip())
        state.active_reservation.nonfree_baggages = int(state.answers["planner.extract_number_of_additional_bags"].strip())
    if state.answers.get("planner.extract_insurance"):
        state.active_reservation.insurance = state.answers["planner.extract_insurance"]

    if not state.user_id:
        return actions.force_output("I'll need your user id to book a flight.")
    if not state.active_reservation.origin:
        return actions.force_output("I'll need your desired origin city to book a flight.")
    if not state.active_reservation.destination:
        return actions.force_output("I'll need your desired destination to book a flight.")
    if not state.active_reservation.flight_type:
        return actions.force_output("I'll need your desired flight type (round trip or one way) to book a flight.")
    if not state.active_reservation.cabin:
        return actions.force_output("I'll need your desired cabin (business, economy, basic economy) to book a flight.")
    if not state.active_reservation.passengers:
        return actions.force_output("I'll need the list of passengers (first name, last name, DOB) to book a flight.")
    if not state.active_reservation.payment_method:
        return actions.force_output("I'll need your payment method to book a flight.")
    if not state.active_reservation.total_baggages:
        return actions.force_output("I'll need your total baggages to book a flight.")
    if not state.active_reservation.nonfree_baggages:
        return actions.force_output("I'll need your nonfree baggages to book a flight.")
    if not state.active_reservation.insurance:
        return actions.force_output("I'll need to know if you want to purchase insurance to book a flight.")

    state.active_reservation.flights = state.searched_flights[0]
    payload = {
        "id": f"call_{state.request_id.split('-')[0]}",
        "type": "function",
        "function": {"name": "book_reservation", "arguments": json.dumps({
            "user_id": state.user_id,
            "origin": state.active_reservation.origin,
            "destination": state.active_reservation.destination,
            "flight_type": state.active_reservation.flight_type,
            "cabin": state.active_reservation.cabin,
            "flights": state.active_reservation.flights,
            "passengers": state.active_reservation.passengers,
            "payment_methods": [state.active_reservation.payment_method],
            "total_baggages": state.active_reservation.total_baggages,
            "nonfree_baggages": state.active_reservation.nonfree_baggages,
            "insurance": state.active_reservation.insurance,
        })},
    }
    return actions.tool_calls(payload)

def call_update_reservation_baggages(actions, state: AppState, tokenizer: Any):
    if not state.active_reservation.reservation_id:
        return actions.force_output("I'll need your reservation id to modify it.")
    if not state.active_reservation.total_baggages:
        return actions.force_output("I'll need your total baggages to modify this reservation.")
    if not state.active_reservation.nonfree_baggages:
        return actions.force_output("I'll need your nonfree baggages to modify this reservation.")
    if not state.active_reservation.payment_method:
        return actions.force_output("I'll need your desired payment method to modify this reservation.")
    payload = {
        "id": f"call_{state.request_id.split('-')[0]}",
        "type": "function",
        "function": {"name": "update_reservation_baggages", "arguments": json.dumps({
            "reservation_id": state.active_reservation.reservation_id,
            "total_baggages": state.active_reservation.total_baggages,
            "nonfree_baggages": state.active_reservation.nonfree_baggages,
            "payment_id": state.active_reservation.payment_method,
        })},
    }
    return actions.tool_calls(payload)


def call_update_reservation_passengers(actions, state: AppState, tokenizer: Any):
    if not state.active_reservation.reservation_id:
        return actions.force_output("I'll need your reservation id to modify it.")
    if not state.active_reservation.passengers:
        return actions.force_output("I'll need the full list of passengers to modify this reservation.")
    payload = {
        "id": f"call_{state.request_id.split('-')[0]}",
        "type": "function",
        "function": {"name": "update_reservation_passengers", "arguments": json.dumps({
            "reservation_id": state.active_reservation.reservation_id,
            "passengers": state.active_reservation.passengers
        })},
    }
    return actions.tool_calls(payload)


def call_get_user_details(actions, state: AppState, tokenizer: Any):
    user_id = (state.user_id or state.answers.get("planner.extract_user_id") or "").strip()
    if not user_id and state.user_details.filled:
        user_id = state.user_details.user_id
        state.user_id = user_id
    if not user_id:
        return force_message(actions, tokenizer, "I'll need your user id to look up the reservation.")
    payload = {
        "id": f"call_{state.request_id.split('-')[0]}" + f"{state.state_hint}" if state.state_hint else "",
        "type": "function",
        "function": {"name": "get_user_details", "arguments": json.dumps({"user_id": user_id})},
    }
    return actions.tool_calls(payload)

def call_get_reservation_details(actions, state: AppState, tokenizer: Any):
    import json
    reservation_id = (state.active_reservation.reservation_id or "").strip()
    if not reservation_id:
        return force_message(actions, tokenizer, "I'll need a valid reservation id to look up the reservation.")
    payload = {
        "id": f"call_{state.request_id.split('-')[0]}" + f"{state.state_hint}" if state.state_hint else "",
        "type": "function",
        "function": {
            "name": "get_reservation_details",
            "arguments": json.dumps({"reservation_id": reservation_id}),
        },
    }
    return actions.tool_calls(payload)


def _as_json(obj: Any) -> Any:
    if isinstance(obj, str):
        try:
            return json.loads(obj)
        except json.JSONDecodeError:
            return None
    return obj

def _normalize_user_details_payload(payload: Any) -> Optional[Dict[str, Any]]:
    data = _as_json(payload)
    if not isinstance(data, dict):
        return None
    if "user_id" in data:
        return data
    if len(data) == 1:
        candidate = next(iter(data.values()))
        if isinstance(candidate, dict) and "user_id" in candidate:
            return candidate
    return None

def _extract_user_details_record(messages: List[Dict[str, Any]]) -> Tuple[Optional[UserDetailsRecord], bool]:
    had_call = False
    for call, response in tool_call_pairs(messages):
        fn = call.get("function")
        if not isinstance(fn, dict) or fn.get("name") != "get_user_details":
            continue
        had_call = True
        record_payload = _normalize_user_details_payload(response)
        if record_payload:

            return (UserDetailsRecord(
                filled=True,
                user_id=str(record_payload.get("user_id", "")),
                name=dict(record_payload.get("name") or {}),
                address=dict(record_payload.get("address") or {}),
                email=str(record_payload.get("email", "")),
                dob=str(record_payload.get("dob", "")),
                payment_methods=dict(record_payload.get("payment_methods") or {}),
                saved_passengers=list(record_payload.get("saved_passengers") or []),
                membership=str(record_payload.get("membership", "")),
                reservations=list(record_payload.get("reservations") or []),
            ), had_call)
    return (None, had_call)


def handle_transfer(messages: Optional[List[Dict[str, Any]]] = None) -> bool:
    source = messages if messages is not None else get_conversation()
    if source:
        if len(source) >= 2:
            if source[-2].get("tool_calls"):
                tool_last = source[-1]["role"] == "tool"
                was_transfer = source[-2]["tool_calls"][0]["function"]["name"] == "transfer_to_human_agents"
                return tool_last and was_transfer
    return False

def handle_update(messages: Optional[List[Dict[str, Any]]] = None) -> (bool, Optional[str]):
    source = messages if messages is not None else get_conversation()
    if source:
        if len(source) >= 2:
            if source[-2].get("tool_calls"):
                tool_last = source[-1]["role"] == "tool"
                was_transfer = source[-2]["tool_calls"][0]["function"]["name"].startswith("update_")
                return tool_last and was_transfer, source[-2]["tool_calls"][0]["function"].get("arguments")
    return (False, None)


def populate_user_details(state: AppState, messages: Optional[List[Dict[str, Any]]] = None) -> (bool, bool):
    if state.user_details.user_id is None:
        source = messages if messages is not None else get_conversation()
        if source:
            (record, had_call) = _extract_user_details_record(source)
            if record is not None:
                state.user_details = record
                state.user_id = record.user_id
            elif had_call:
                return (True, source[-1]["role"] == "tool")
    return (False, False)


# --- Reservation details helpers ---

POLICY_NOW_EST = "2024-05-15 15:00:00 EST"


def _parse_policy_now() -> Any:
    # Strip timezone for naive parsing
    ts = POLICY_NOW_EST.replace(" EST", "")
    try:
        from datetime import datetime
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _parse_iso_dt(ts: str) -> Optional[Any]:
    try:
        from datetime import datetime
        if "T" in ts:
            return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _extract_reservation_details_records(messages: List[Dict[str, Any]]) -> List[ReservationDetailsRecord]:
    records: List[ReservationDetailsRecord] = []
    for call, response in tool_call_pairs(messages):
        fn = call.get("function") if isinstance(call, dict) else None
        if not isinstance(fn, dict) or fn.get("name") != "get_reservation_details":
            continue
        data = _as_json(response)
        if not isinstance(data, dict):
            continue
        rid = str(data.get("reservation_id")) if data.get("reservation_id") is not None else None
        rec = ReservationDetailsRecord(
            reservation_id=rid,
            user_id=str(data.get("user_id", "")) if data.get("user_id") is not None else None,
            created_at=str(data.get("created_at", "")) if data.get("created_at") is not None else None,
            cabin=str(data.get("cabin", "")) if data.get("cabin") is not None else None,
            flights=list(data.get("flights") or []),
            insurance=str(data.get("insurance", "")) if data.get("insurance") is not None else None,
            status=str(data.get("status", "")) if data.get("status") is not None else None,
            passengers=list(data.get("passengers") or []),
            payment_history=list(data.get("payment_history") or []),
            total_baggages=int(data.get("total_baggages")) if isinstance(data.get("total_baggages"), int) else None,
            nonfree_baggages=int(data.get("nonfree_baggages")) if isinstance(data.get("nonfree_baggages"), int) else None,
        )
        records.append(rec)
    return records


def populate_reservation_details(state: AppState, messages: Optional[List[Dict[str, Any]]] = None) -> None:
    source = messages if messages is not None else get_conversation()
    if not source:
        return
    records = _extract_reservation_details_records(source)
    if not records:
        return
    for rec in records:
        rid = rec.reservation_id
        if not rid:
            continue
        # Cache every record we see
        state.reservations[rid] = rec



def is_within_24_hours(created_at: Optional[str]) -> Optional[bool]:
    if not created_at:
        return None
    now = _parse_policy_now()
    created = _parse_iso_dt(created_at)
    if not now or not created:
        return None
    try:
        delta = now - created
        return 0 <= delta.total_seconds() <= 24 * 3600
    except Exception:
        return None


# --- Flight status helpers ---

def _extract_flight_status_updates(messages: List[Dict[str, Any]]) -> Dict[str, str]:
    updates: Dict[str, str] = {}
    for call, response in tool_call_pairs(messages):
        fn = call.get("function") if isinstance(call, dict) else None
        if not isinstance(fn, dict) or fn.get("name") != "get_flight_status":
            continue
        # Parse args to build key
        args_raw = fn.get("arguments")
        flight_number = None
        date = None
        try:
            parsed = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw or {})
            flight_number = parsed.get("flight_number")
            date = parsed.get("date") or parsed.get("reservation_date")
        except Exception:
            pass
        if not flight_number or not date:
            continue
        key = f"{flight_number}|{date}"
        # Parse response for status
        status = None
        data = _as_json(response)
        if data:
            if isinstance(data, dict):
                s = data.get("status")
                if isinstance(s, str) and s:
                    status = s.lower()
            elif isinstance(data, str):
                status = data.lower()
        elif response:
            status = response.lower()
        if status:
            updates[key] = status
    return updates


def populate_flight_status(state: AppState, messages: Optional[List[Dict[str, Any]]] = None) -> None:
    source = messages if messages is not None else get_conversation()
    if not source:
        return
    updates = _extract_flight_status_updates(source)
    if updates:
        state.flight_status.update(updates)


def flight_has_flown(status: Optional[str]) -> Optional[bool]:
    if not status:
        return None
    s = status.lower()
    if s in ("flying", "landed"):
        return True
    if s in ("available", "on time", "delayed", "cancelled"):
        return False
    return None


def encode_text(tokenizer: Any, text: str) -> List[int]:
    if hasattr(tokenizer, "encode"):
        ids = tokenizer.encode(text, add_special_tokens=False)
    elif callable(tokenizer):
        ids = tokenizer(text)
    else:
        raise RuntimeError("Tokenizer does not support encode")
    assert isinstance(ids, list), "Tokenizer did not return a list"
    return [int(t) for t in ids]


def force_message(actions, tokenizer: Any, text: str):
    payload = text if text.endswith("\n") else text + "\n"
    tokens = encode_text(tokenizer, payload)
    eos_id = getattr(tokenizer, "eos_token_id", None)
    if eos_id is not None:
        tokens.append(int(eos_id))
    return actions.force_tokens(tokens)


def tool_payload(function_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    import json
    return {
        "id": f"call_generic",
        "type": "function",
        "function": {"name": function_name, "arguments": json.dumps(arguments)},
    }


__all__ = [
    "encode_text",
    "force_message",
    "tool_payload",
    "populate_user_details",
    "populate_reservation_details",
    "populate_flight_status",
    "is_within_24_hours",
    "flight_has_flown",
]
