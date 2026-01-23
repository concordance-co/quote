import logging
from typing import Optional

logger = logging.getLogger(__name__)

from examples.tau2.utils import (
    call_list_all_airports,
    call_search_flight,
    call_book_flight_reservation,
    call_update_reservation_passengers,
    call_update_reservation_baggages,
    call_update_reservation_flights,
    call_get_flight_status,
    call_get_user_details,
    call_get_reservation_details,
    flight_has_flown,
    call_cancel_reservation,
    is_within_24_hours,
    transfer_flow
)
from examples.tau2.state import ActiveReservation, StateHint, AppState
from quote_mod_sdk.strategies.strategy_constructor import ChoicesStrat, ListStrat, UntilStrat, CharsStrat, CharsMode
from quote_mod_sdk.strategies.primitives import UntilEndType
from quote_mod_sdk.flow import FlowQuestion, RouteTarget, route_noop, route_message, route_output, route_tool, route_question
from quote_mod_sdk.self_prompt import EraseMode
from quote_mod_sdk.conversation import get_conversation


def gen_flight(ctx: AppState, target):
    nums = ctx.answers["planner.extract_flight_number"]
    ctx.answers["planner.extract_flight_number"] = "HAT" + nums


    return target

def gen_date(ctx: AppState, info: str, target):
    info_t = info.replace(" ", "_")
    gen_year = FlowQuestion(
        name=f"planner.extract_year_of_{info_t}",
        prompt=f" What is the year of {info}:",
        strategy=CharsStrat(CharsMode.NUMERIC, min=4, stop=4),
    )
    gen_month = FlowQuestion(
        name=f"planner.extract_month_of_{info_t}",
        prompt=f" What is the month of {info} (in MM):",
        strategy=CharsStrat(CharsMode.NUMERIC, min=2, stop=2),
    )
    gen_day = FlowQuestion(
        name=f"planner.extract_day_of_{info_t}",
        prompt=f" What is the day of {info} (in DD):",
        strategy=CharsStrat(CharsMode.NUMERIC, min=2, stop=2),
    )

    def handle_combining(ctx: AppState, target):
        ctx.answers[f"planner.extract_date_of_{info_t}"] = ctx.answers[f"planner.extract_year_of_{info_t}"] + "-" + ctx.answers[f"planner.extract_month_of_{info_t}"] + "-" + ctx.answers[f"planner.extract_day_of_{info_t}"]
        return target
    gen_year.then(gen_month.then(gen_day.then(lambda ctx: handle_combining(ctx, target))))
    return gen_year


def gen_flight_num(ctx: AppState, target):
    gen_flight_num_q = FlowQuestion(
        name="planner.extract_flight_number",
        prompt=" What are the digits that complete this flight number? HAT",
        strategy=CharsStrat(CharsMode.NUMERIC, min=3, stop=3)
    ).then(lambda ctx: gen_date(ctx, "the flight", lambda ctx1: gen_flight(ctx1, target)))
    return gen_flight_num_q


def _within_branch(ctx: AppState):
     if not ctx.active_reservation.reservation_id:
         return transfer_flow(ctx, "No reservation details")
     reservation_details = ctx.reservations.get(ctx.active_reservation.reservation_id)
     if not reservation_details:
         return transfer_flow(ctx, "No reservation details")
     if reservation_details.created_at:
         res = is_within_24_hours(reservation_details.created_at)
         if res is True:
             return user_confirm_cancel(ctx)
         if res is False:
             return _biz_branch(ctx)
     return transfer_flow(ctx, "No reservation details")

 # Auto-evaluate business cabin from reservation details
def _biz_branch(ctx: AppState):
    if not ctx.active_reservation.reservation_id:
        return transfer_flow(ctx, "No reservation details")
    reservation_details = ctx.reservations.get(ctx.active_reservation.reservation_id)
    cabin = (reservation_details.cabin or "").lower() if reservation_details else None
    if cabin:
        if cabin == "business":
            return user_confirm_cancel(ctx)
        return _ins_branch(ctx)
    return transfer_flow(ctx, "Missing cabin class")

 # If no insurance in reservation details, short-circuit to denial; otherwise fall back to asking.
def _ins_branch(ctx: AppState):
    if not ctx.active_reservation.reservation_id:
        return transfer_flow(ctx, "No reservation details")
    reservation_details = ctx.reservations.get(ctx.active_reservation.reservation_id)
    if not reservation_details:
        return transfer_flow(ctx, "No reservation details")
    if reservation_details.insurance and reservation_details.insurance != "no":
        if ctx.active_reservation.cancel_reason and (ctx.active_reservation.cancel_reason == "weather" or ctx.active_reservation.cancel_reason == "health"):
            return user_confirm_cancel(ctx)
        elif not ctx.active_reservation.cancel_reason:
            reason = FlowQuestion(
                name="planner.cancel_reason",
                prompt=" What is the reason for cancellation? (weather, health, other): ",
                strategy=ChoicesStrat(["weather", "health", "other"]),
                erase_mode=EraseMode.ALL
            ).assign(
                lambda ctx, ans: setattr(ctx.active_reservation, "cancel_reason", (ans or "").strip().lower())
            ).branch(_ins_branch)
            return reason
    else:
        id = ctx.active_reservation.reservation_id
        ctx.active_reservation = ActiveReservation()
        ctx.transfer_reason = None
        return route_output(f"Per policy, I cannot process the cancellation for the reservation {id} via insurance since no insurance was purchased or the reason given is not covered by insurance. Is there anything else I can help you with?")


def any_flown(ctx: AppState):
    if not ctx.active_reservation.reservation_id:
        return transfer_flow(ctx, "No reservation details")
    reservation_details = ctx.reservations.get(ctx.active_reservation.reservation_id)
    if reservation_details is not None:
        res_flights = reservation_details.flights
        seg = res_flights[0] or {}
        fn = seg.get("flight_number") or seg.get("flight") or seg.get("number")
        dt = seg.get("date")
        if fn and dt:
            key = f"{fn}|{dt}"
            status = ctx.flight_status.get(key)
            flown = flight_has_flown(status)
            if flown is True:
                return transfer_flow(ctx, "User has already flown a portion of the flight")
            if flown is False:
                return user_confirm_cancel(ctx) if status == "cancelled" else _within_branch(ctx)
            return route_tool(call_get_flight_status)
    return transfer_flow(ctx, "No flights for reservation")

def user_confirm_cancel(ctx: AppState):
    conf = FlowQuestion(
        name="cancel.confirm",
        prompt=f" Has the user reconfirmed that they want to cancel the reservation {ctx.active_reservation.reservation_id} (yes/abort/unsure): ",
        strategy=ChoicesStrat(["proceed", "abort", "unsure"]),
        erase_mode=EraseMode.ALL
    ).with_auto_answer(lambda ctx: ctx.cancel.confirmed if ctx.cancel.confirmed else "unsure")
    conf.on("yes", route_tool(call_cancel_reservation))
    conf.on("abort", lambda ctx: (setattr(ctx.active_reservation, "reservation_id", None), route_message("Okay, I won't proceed with cancellation. What else can I help you with?"))[1])
    conf.on("unsure", route_message(f"Can you confirm you want to cancel the reservation {ctx.active_reservation.reservation_id}?"))
    return route_question(conf)

def clarify(what_to_clarify: str, target: RouteTarget | None, state: AppState):

    prompt = f"\nI need more information from the user about {what_to_clarify}. I should only ask about that. I should wrap my question in XML (starting with <question_to_user>) so the client-side chat can process it so I should say (I must close the question tag with </question_to_user> when done) about {what_to_clarify}: ";
    what_to_clarify_name = what_to_clarify.replace(" ", "_")
    clarify_q = FlowQuestion(
        name=f"planner.clarify_{what_to_clarify_name}",
        prompt=prompt,
        strategy=UntilStrat("<question_to_user>", UntilEndType.TAG, "</question_to_user>"),
    )
    if target is not None:
        clarify_q.branch(target)
    else:
        clarify_q.then(lambda ctx: route_output("Let me ask a clarifying question: " + ctx.answers[f"planner.clarify_{what_to_clarify_name}"][len("<question_to_user>"):-1*len("</question_to_user>")].strip()))
    return clarify_q

def book_flight(ctx: AppState):
    get_flight_type(
        get_cabin_change(
            ctx,
            get_origin(
                ctx,
                get_date(
                    ctx,
                    get_destination(
                        ctx,
                        extract_passenger(
                            get_payment_id(
                                ctx,
                                get_add_baggage(
                                    ctx,
                                    get_wants_insurance(
                                        route_tool(call_book_flight_reservation)
                                    )
                                )
                            ),
                            clarify("the full name and date of birth of each passenger", None, ctx),
                            ctx
                        ) if len(ctx.searched_flights) > 0 else route_tool(call_search_flight)
                    )
                )
            )
        )
    )


def extract_value_and_goto(what_to_extract: str, good_target: RouteTarget, empty_target: RouteTarget, state: AppState, extra_info: Optional[str]):
    logger.debug("extracting %s", what_to_extract)
    original = what_to_extract
    what_to_extract = what_to_extract.replace(" ", "_")
    prompt = f" I need to extract information about {original} from the users messages."
    prompt += f"{extra_info}" if extra_info else ""
    prompt += f" I need to format the data into XML for: {original}. If {original} was not provided by the user, the xml should be empty:\n"
    logger.debug("extract prompt: %s", prompt)
    extract = FlowQuestion(
        name=f"planner.extract_{what_to_extract}",
        prompt=prompt,
        strategy=UntilStrat(f"<{what_to_extract}>", UntilEndType.TAG, f"</{what_to_extract}>"),
        # erase_mode="all"
    )
    def check_answer(ctx: AppState):
        ans = ctx.answers[f"planner.extract_{what_to_extract}"]
        ctx.answers[f"planner.extract_{what_to_extract}"] = ans[len(f"<{what_to_extract}>"):].split(f"</{what_to_extract}>")[0].strip()
        logger.debug("GOT ANSWER: %s", ctx.answers[f"planner.extract_{what_to_extract}"])
        if ctx.answers[f"planner.extract_{what_to_extract}"] == "UNKNOWN" or len(ctx.answers[f"planner.extract_{what_to_extract}"]) == 0:
            return empty_target
        if ans:
            return good_target
        else:
            return empty_target
    return extract.branch(lambda ctx: check_answer(ctx))

def raw_any_flown(ctx: AppState, has_not_flown_target: RouteTarget, has_flown_target: RouteTarget):
    if not ctx.active_reservation.reservation_id:
        return transfer_flow(ctx, "No reservation details")
    reservation_details = ctx.reservations.get(ctx.active_reservation.reservation_id)
    if reservation_details is not None:
        res_flights = reservation_details.flights
        seg = res_flights[0] or {}
        fn = seg.get("flight_number") or seg.get("flight") or seg.get("number")
        dt = seg.get("date")
        if fn and dt:
            key = f"{fn}|{dt}"
            status = ctx.flight_status.get(key)
            flown = flight_has_flown(status)
            if flown:
                return has_flown_target(ctx)
            else:
                return has_not_flown_target(ctx)
    return transfer_flow(ctx, "No reservation details")


ask_about_flight_status = lambda ctx: clarify(f"what they would like to know from this summary of the flight information: {ctx.answers.get("planner.extract_flight_number")}", None, ctx)
ask_which_reservation = lambda ctx: clarify("what reservation I need to take action on", None, ctx)
ask_which_flight = lambda ctx: clarify("what flight number I need information on", None, ctx)
ask_user_id = lambda ctx: clarify("what the user's id is", None, ctx)
ask_desired_cabin_type = lambda ctx: clarify("what the user's desired cabin type is", None, ctx)
ask_trip_origin = lambda ctx: clarify("what the trip's origin is", None, ctx)
ask_trip_date = lambda ctx: clarify("what the trip's date is", None, ctx)
ask_trip_dest = lambda ctx: clarify("what the trip's destination is", None, ctx)
ask_payment_id = lambda ctx: clarify("what the trip's payment method is", None, ctx)
ask_number_of_additional_bags = lambda ctx: clarify("how many more bags to add to the reservation", None, ctx)


has_user_id = lambda ctx, yes_target, no_target: FlowQuestion(
    name="planner.has_user_id",
    prompt=f" Did the user provide their user id (yes/no): ",
    strategy=ChoicesStrat(["yes", "no"]),
    erase_mode=EraseMode.ALL
).on("yes", yes_target).on("no", no_target)


has_airports = lambda ctx, yes_target: FlowQuestion(
    name="planner.has_airports",
    prompt=f" Have I called the list_all_airports function: ",
    strategy=ChoicesStrat(["yes", "no"]),
    erase_mode=EraseMode.ALL
).on("yes", yes_target(ctx)).on("no", route_tool(call_list_all_airports))

get_confirmed = lambda target, what: FlowQuestion(
    name="planner.confirmation",
    prompt=f" Did the user confirmed they want to {what} (yes/aborted/not yet): ",
    strategy=ChoicesStrat(["yes", "aborted", "not yet"]),
    erase_mode=EraseMode.ALL
).then(target)


def extract_passenger(good_target: RouteTarget, empty_target: RouteTarget, state: AppState):
    extract = FlowQuestion(
        name=f"planner.extract_passenger",
        prompt=f" I need to format the passenger data into XML. It needs to be in the form <data>\n\t<Passenger>\n\t\t<FirstName>Name</FirstName>\n\t\t<LastName>Name</LastName>\n\t\t<DateOfBirth>YYYY-MM-DD</DateOfBirth>\n\t</Passenger>\n</data>:\n",
        strategy=UntilStrat("<data>", UntilEndType.TAG, "</data>"),
        erase_mode=EraseMode.ALL
    )
    def check_answer(ctx: AppState):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(ctx.answers[f"planner.extract_passenger"])
        logger.debug("root: %s", root)
        # ctx.answers[f"planner.extract_passenger"] = ans[len(f"<{what_to_extract}>"):].split(f"</{what_to_extract}>")[0]
        logger.debug("GOT ANSWER: %s", ctx.answers[f"planner.extract_passenger"])
        # if ctx.answers[f"planner.extract_{what_to_extract}"].strip() == "UNKNOWN":
        #     return empty_target
        # if ans:
        #     return good_target
        # else:
        return empty_target
    return extract.branch(lambda ctx: check_answer(ctx))

get_wants_insurance = lambda target: FlowQuestion(
    name="planner.extract_insurance",
    prompt=f" The user wants to purchase insurance (yes/no): ",
    strategy=ChoicesStrat(["yes", "no"]),
    erase_mode=EraseMode.ALL
).then(target)

def extract_user_id(ctx, good_target):
    if ctx.user_details.user_id:
        ctx.answers["planner.extract_user_id"] = ctx.user_details.user_id
        return good_target(ctx)
    else:
        return extract_value_and_goto(
            "user id",
            good_target,
            lambda ctx: ask_user_id(ctx),
            ctx,
            None
        )

get_add_baggage = lambda ctx, good_target: extract_value_and_goto("number of additional bags", good_target, lambda ctx: ask_number_of_additional_bags(ctx), ctx, None)
get_cabin_change = lambda ctx, good_target: extract_value_and_goto("desired cabin type", good_target, lambda ctx: ask_desired_cabin_type(ctx), ctx, None)
get_user_id = lambda ctx, good_target: (
    has_user_id(
        ctx,
        lambda ctx: extract_user_id(ctx, good_target),
        lambda ctx: ask_user_id(ctx)
    ) if ctx.user_id is None and ctx.user_details.user_id is None else good_target
)
get_origin = lambda ctx, good_target: extract_value_and_goto("trip origin", good_target, lambda ctx: ask_trip_origin(ctx), ctx, None)
get_date = lambda ctx, good_target: extract_value_and_goto("date of trip", good_target, lambda ctx: ask_trip_date(ctx), ctx, None)
get_destination = lambda ctx, good_target: extract_value_and_goto("trip destination", good_target, lambda ctx: ask_trip_dest(ctx), ctx, None)
get_payment_id = lambda ctx, good_target: extract_value_and_goto("payment id", good_target, lambda ctx: ask_payment_id(ctx), ctx, None)
get_flight_type = lambda target: FlowQuestion(
    name="planner.flight_type",
    prompt=f" The type of flight is (round trip/one way): ",
    strategy=ChoicesStrat(["round_trip", "one_way"]),
    erase_mode=EraseMode.ALL
).then(target)
get_cabin = lambda target: FlowQuestion(
    name="planner.cabin_type",
    prompt=f" The cabin type is (bussiness/economy/basic economy): ",
    strategy=ChoicesStrat(["business", "economy", "basic_economy"]),
    erase_mode=EraseMode.ALL
).then(target)
get_user_details = lambda ctx, target: route_tool(call_get_user_details) if not ctx.user_details.filled else target

def get_reservation_details(ctx: AppState, target: RouteTarget | None):
    ctx.active_reservation.reservation_id = ctx.answers["planner.extract_reservation_id_to_act_on"]
    if not ctx.active_reservation.reservation_id:
        return ask_which_reservation(ctx)
    if not ctx.reservations.get(ctx.active_reservation.reservation_id):
        return route_tool(call_get_reservation_details)
    return target

def fn_flight_status(ctx: AppState, target: RouteTarget | None):
    flight_number = ctx.answers.get("planner.extract_flight_number")
    flight_date = ctx.answers.get("planner.extract_flight_date")
    if not flight_number:
        return ask_which_flight(ctx)
    if not flight_date:
        return get_date(ctx, fn_flight_status)
    if not ctx.flight_status.get(flight_number):
        return route_tool(call_get_flight_status)
    return target


select_reservation = lambda ctx, target: extract_value_and_goto("reservation id to act on", lambda ctx: get_reservation_details(ctx, target), ask_which_reservation, ctx, " It should be a single reservation ID - do not include multiple.")

def get_flight_status(ctx: AppState):
    return FlowQuestion(
        name="planner.has_flight_number",
        prompt=" Did the user provide a flight number to get status of (yes/no): ",
        strategy=ChoicesStrat(["yes", "no"]),
        erase_mode=EraseMode.ALL
    ).on(
        "yes", lambda ctx: gen_flight_num(ctx, lambda ctx1: ask_about_flight_status(ctx1))
    ).on(
        "no", lambda ctx: ask_which_flight(ctx)
    )

def get_all_reservation_details(ctx: AppState, target: RouteTarget | None):
    if not ctx.user_details.reservations:
        return route_tool(call_get_user_details)
    for reservation in ctx.user_details.reservations:
        if not ctx.reservations.get(reservation):
            ctx.active_reservation.reservation_id = reservation
            return route_tool(call_get_reservation_details)
    if target:
        return target(ctx)


def inject_reservation_info(ctx: AppState):
    return FlowQuestion(
        name=f"planner.extract_res_info",
        prompt=f" I need to extract data into xml for the reservation_info the user requested (I must close the extracted tag with </reservation_info> when done. If it is unknown, immediately close the xml tag). Here is all of the user's reservations: {ctx.reservations}:\n",
        strategy=UntilStrat("<extracted value_kind=\"reservation_info\">", UntilEndType.TAG,  "</extracted>"),
        erase_mode=EraseMode.ALL
    ).then(lambda ctx: route_output(f"Here is the information I found for that reservation: {ctx.answers["planner.extract_res_info"]}"))


def gate_not_basic_economy(ctx: AppState, not_be_target: RouteTarget, is_be_target: RouteTarget):
    if ctx.active_reservation.reservation_id:
        rezzy = ctx.reservations.get(ctx.active_reservation.reservation_id)
        if rezzy:
            ctx.active_reservation.basic_economy = rezzy.cabin == "basic_economy"
            if ctx.active_reservation.basic_economy:
                return is_be_target
            else:
                return not_be_target
        else:
            return route_tool(call_get_reservation_details)
    else:
        return clarify("what the reservation id is", None, ctx)

def modify_flight(ctx: AppState):
    orig_and_dest = lambda ctx, target: get_origin(ctx, lambda ctx1: get_destination(ctx1, target))
    builder = orig_and_dest
    if not ctx.active_reservation.cabin and not ctx.answers.get("planner.cabin_type"):
        builder = lambda ctx, target: builder(ctx, get_cabin(target))
    if not ctx.active_reservation.payment_method and not ctx.answers.get("planner.extract_payment_id"):
        builder = lambda ctx, target: builder(ctx, get_payment_id(ctx, target))
    return transfer_flow(ctx, "Agent is unable to process this")


def modify_cabin(ctx: AppState):
    ctx.active_reservation.total_baggages = ctx.reservations[ctx.active_reservation.reservation_id].total_baggages
    ctx.active_reservation.nonfree_baggages = ctx.reservations[ctx.active_reservation.reservation_id].nonfree_baggages
    ctx.active_reservation.flights = ctx.reservations[ctx.active_reservation.reservation_id].flights
    ctx.active_reservation.passengers = ctx.reservations[ctx.active_reservation.reservation_id].passengers
    return raw_any_flown(
        ctx,
        lambda ctx1: get_cabin_change(
            ctx1,
            lambda ctx2: (
                setattr(ctx2.active_reservation, "cabin", ctx2.answers["planner.extract_desired_cabin_type"]),
                get_confirmed(
                    lambda ctx3: get_payment_id(
                        ctx3,
                        lambda ctx4: (
                            setattr(ctx4.active_reservation, "payment_method", ctx4.answers["planner.extract_payment_id"]),
                            route_tool(call_update_reservation_flights)
                        )[1]
                    ),
                    f"modify cabin to {ctx1.answers["planner.extract_desired_cabin_type"]}"
                )
            )[1]
        ),
        lambda ctx1: transfer_flow(ctx1, "Has already flown a segment")
    )

def modify_baggage(ctx: AppState):
    ctx.active_reservation.flights = ctx.reservations[ctx.active_reservation.reservation_id].flights
    ctx.active_reservation.cabin = ctx.reservations[ctx.active_reservation.reservation_id].cabin
    ctx.active_reservation.passengers = ctx.reservations[ctx.active_reservation.reservation_id].passengers
    return get_add_baggage(ctx,
        lambda ctx1: get_payment_id(
            ctx1,
            lambda ctx2: get_confirmed(
                lambda ctx2: (
                    setattr(ctx1.active_reservation, "total_baggages", ctx.reservations[ctx.active_reservation.reservation_id].total_baggages + ctx1.answers["planner.number_of_additional_bags"]),
                    route_tool(call_update_reservation_baggages)
                )[1],
                f"add {ctx1.answers["planner.number_of_additional_bags"]} bags to the reservation"
            )
        )
    )

def modify_passengers(ctx: AppState):
    ctx.active_reservation.passengers = ctx.reservations[ctx.active_reservation.reservation_id].passengers
    return extract_passenger(ctx, route_tool(call_update_reservation_passengers), clarify("the full list of passengers", ctx))

def modify_router(ctx: AppState):
    return FlowQuestion(
        name="planner.modify_router",
        prompt=f" Based on the current state of the conversation I should (ask for clarification, help modify flight, help modify passengers, help modify cabin, help modify baggage, help modify insurance): ",
        strategy=ChoicesStrat([
            "ask for clarification",
            "help modify flight",
            "help modify passengers",
            "help modify cabin",
            "help modify baggage",
            "help modify insurance"
        ]),
        erase_mode=EraseMode.ALL
    ).on(
        "ask for clarification", lambda ctx: clarify("what the user would like to modify (flight, passengers, cabin, baggage, insurance)", None, ctx)
    ).on(
        "help modify flight", lambda ctx: gate_not_basic_economy(ctx, lambda ctx2: modify_flight(ctx2), lambda ctx2: route_output("I am sorry, I am unable to modify the flight of a basic economy reservation. Is there anything else I can help with?"))
    ).on(
        "help modify passengers", lambda ctx: modify_passengers(ctx)
    ).on(
        "help modify cabin", lambda ctx:  modify_cabin(ctx)
    ).on(
        "help modify baggage", lambda ctx: modify_baggage(ctx)
    ).on(
        "help modify insurance", lambda ctx: route_output("I am sorry, insurance can only be purchased at time of booking. Is there anything else I can help with?")
    )


def handle_route(ctx: AppState):
    route = ctx.answers["planner.router"]
    if route == "1 ask for clarification":
        ctx.state_hint = StateHint.CLARIFY
        return clarify("if i should find reservation information, cancel a reservation, modify a reservation, book a flight, get flight status, or transfer to human agent", None, ctx)
    elif route == "2 find reservation information":
        ctx.state_hint = StateHint.RES_INFO
        return get_user_id(ctx, lambda ctx1: get_all_reservation_details(ctx1, inject_reservation_info))
    elif route == "3 cancel reservation":
        ctx.state_hint = StateHint.CANCEL
        return get_user_id(ctx, lambda ctx1: get_user_details(ctx1, lambda ctx2: select_reservation(ctx2, lambda ctx3: any_flown(ctx3))))
    elif route == "4 modify reservation":
        ctx.state_hint = StateHint.MODIFY
        return get_user_id(ctx, lambda ctx1: get_user_details(ctx1, lambda ctx2: select_reservation(ctx2, lambda ctx3: modify_router(ctx3))))
    elif route == "5 book flight":
        ctx.state_hint = StateHint.BOOK
        return get_user_id(ctx, lambda ctx1: get_user_details(ctx1, lambda ctx2: select_reservation(ctx2, lambda ctx3: has_airports(ctx, book_flight(ctx3)))))
    elif route == "6 transfer_to_human":
        return transfer_flow(ctx, "user requested human assistance")
    elif route == "7 flight status":
        ctx.state_hint = StateHint.STATUS
        return get_flight_status(ctx)


def continue_route(ctx: AppState):
    state_hint = None
    source = get_conversation()
    for i in source[-1:]:
        if source[i].get("tool_calls"):
            if source[i]["role"] == "tool":
                hint = source[-1]["tool_call_id"].split(".")
                state_hint = hint[1] if 1 < len(hint) else None
                if state_hint:
                    break
    if state_hint == "RES_INFO":
        ctx.state_hint = StateHint.RES_INFO
        return "2 find reservation information"
    elif state_hint == "CANCEL":
        ctx.state_hint = StateHint.CANCEL
        return "3 cancel reservation"
    elif state_hint == "MODIFY":
        ctx.state_hint = StateHint.MODIFY
        return "4 modify reservation"
    elif state_hint == "BOOK":
        ctx.state_hint = StateHint.BOOK
        return "5 book flight"
    return None


def router(ctx: AppState):
    return FlowQuestion(
        name="planner.router",
        prompt=f""" I now need to route my thinking to better serve the user.
Here are my capabilities:
    1. Find a reservation ID based on user id and a flight via `find_reservation_id`
    2. Cancel a reservation via `cancel_reservation`
    3. Modify a reservation (flights, passengers, baggage, cabin, insurance) via `modify_reservation`
    4. Answer questions about a flight via `flight_status`
    5. Book a new flight via `book_flight`
    6. Transfer to a human agent when the user requests it via `transfer_to_human`
    7. General chat via `other`

I should try to exhaust my capabilities before transfering to a human.

I should determine what I should do that will best serve the user:
    1. ask for clarification (if i should find reservation information, cancel a reservation, modify a reservation, book a flight, get flight status, or transfer to human agent)
    2. find reservation information (if the user says they dont know their reservation id)
    3. cancel reservation (if the user says they want to cancel a flight/reservation)
    4. modify reservation (modify flights, passengers, baggage, cabin)
    5. book flight (if the user says they want to book a flight)
    6. flight status (if the user asks for flight status)
    7. transfer_to_human (the user explicitly requests talking to a human)
    8. other

Note to self: a cancellation is not a modification - they are different actions.

I should route my thinking towards: """,
        strategy=ChoicesStrat([
            "1 ask for clarification",
            "2 find reservation information",
            "3 cancel reservation",
            "4 modify reservation",
            "5 book flight",
            # "6 transfer_to_human",
            "7 flight status"
        ]),
        # erase_mode=EraseMode.ALL
    ).with_auto_answer(lambda ctx: continue_route(ctx)).branch(lambda ctx: handle_route(ctx))


entry_prompt = """
I am configured to talk to myself to answer questions and think step by step to help the user achieve what they want while staying within my defined policy.

The user may want to do multiple actions on multiple reservations. I always need to keep in mind what the current reservation we are working is.

The flow I follow should be to ask myself a series of questions that eventually result in either asking the user for more information or taking some action.
First I will ask if I know the user's intent. Then I will route my thinking to a few paths:
    1. asking for clarification from the user
        - This is useful if its unclear how I should route my thinking. If the user's intent is clear (i.e. they have state they want to cancel a reservation), I don't need to
          use this. I will ask clarifying questions in the other flows when necessary.
    2. help find reservation information
        - This is for when the user needs information about a reservation or flight
    3. cancel reservation
        - This is for when the user wants to cancel a reservation.
    4. modify/change aspects of a reservation
        - This is for when the user wants to make a change to an existing reservation. Notably, cancellation is NOT a modification. Modifications can be baggage, cabin, flight segment, insurance, or passenger changes.
        - The user may want to modify multiple aspects of a reservation
        - They could ask to change the name of a passenger
        - They could ask to change the cabin type
        - They could ask to add bags
        - They could ask to buy insurance
        - They could ask to change a flight
    5. book a flight
        - This is for when the user wants to book an entirely new flight.


A user has the following data associated with them:
    1. a user id/user name
    2. a list of reservations
    3. flight(s) for each reservation
    4. passenger(s) for each reservation
    5. baggage(s) for each reservation
    6. cabin for each reservation
    7. payment ids

When I route to modifying a reservation, I will enter another thinking router to help accomplish the task.

If I have asked a question to the user previous, do not repeat it.

I must keep in mind what the overarching goal of the user is. If I asked a question, I need to make sure after I receive a response that I keep in mind that what the user wants to do has already been stated.

I will need to produce XML to extract information at various points. It is extremely important that if the user did not provide the data/information that the value inside the XML tags is empty. This helps guide my future decisions.

If I say I need more information about something and begin to ask the user a question, make the question directly asks about what information I need.

I am going to now begin this step-by-step thinking process:

Broadly has the user expressed what they would like to do?
"""
entry = FlowQuestion(
    name="planner.know_intent",
    prompt=entry_prompt,
    strategy=ChoicesStrat(["yes"]),
    # erase_mode=EraseMode.PROMPT
).on(
    "yes",  lambda ctx: router(ctx)
)
