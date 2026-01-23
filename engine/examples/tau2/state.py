from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum, auto
from quote_mod_sdk.flow import FlowQuestion, FlowRoute


class StateHint(Enum):
    CLARIFY = auto()
    RES_INFO = auto()
    CANCEL = auto()
    MODIFY = auto()
    BOOK = auto()
    STATUS = auto()


@dataclass
class UserDetailsRecord:
    filled: bool = False
    user_id: Optional[str] = None
    name: Optional[Dict[str, Any]] = None
    address: Optional[Dict[str, Any]] = None
    email: Optional[str] = None
    dob: Optional[str] = None
    payment_methods: Optional[Dict[str, Any]] = None
    saved_passengers: Optional[List[Dict[str, Any]]] = None
    membership: Optional[str] = None
    reservations: Optional[List[str]] = None

@dataclass
class ReservationDetailsRecord:
    reservation_id: Optional[str] = None
    user_id: Optional[str] = None
    created_at: Optional[str] = None
    cabin: Optional[str] = None
    flights: Optional[List[Dict[str, Any]]] = None
    insurance: Optional[str] = None
    status: Optional[str] = None
    passengers: Optional[List[Dict[str, Any]]] = None
    payment_history: Optional[List[Dict[str, Any]]] = None
    total_baggages: Optional[int] = None
    nonfree_baggages: Optional[int] = None


@dataclass
class ActiveReservation:
    reservation_id: Optional[str] = None
    basic_economy = False
    payment_method: Optional[str] = None
    cabin: Optional[str] = None
    action: Optional[str] = None
    cancel_reason: Optional[str] = None
    confirmed: bool = False
    modification_kind: Optional[str] = None
    total_baggages: Optional[int] = None
    nonfree_baggages: Optional[int] = None
    flights: Optional[dict] = None
    passengers: Optional[list[dict]] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    insurance: Optional[str] = None
    flight_type: Optional[str] = None

@dataclass
class AppState:
    # FlowState protocol fields
    request_id: str = ""
    current_question: Optional[FlowQuestion] = None
    pending_route: Optional[FlowRoute] = None
    answers: Dict[str, str] = field(default_factory=dict)
    data: Dict[str, Any] = field(default_factory=dict)

    state_hint: StateHint = None
    transfer_reason: Optional[str] = None
    user_id: Optional[str] = None
    user_details: UserDetailsRecord = field(default_factory=UserDetailsRecord)
    reservations: Dict[str, ReservationDetailsRecord] = field(default_factory=dict)
    flight_status: Dict[str, str] = field(default_factory=dict)
    active_reservation: ActiveReservation = field(default_factory=ActiveReservation)
    searched_flights: list[Any] = field(default_factory=list)

__all__ = [
    "UserDetailsRecord",
    "ReservationDetailsRecord",
    "AppState",
    "ActiveReservation"
]
