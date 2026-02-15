from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
    Protocol,
    runtime_checkable,
    TypeVar,
    Generic,
    cast,
)

from shared.types import Backtrack

from sdk.quote_mod_sdk.self_prompt import SelfPrompt
from sdk.quote_mod_sdk import ActionBuilder, Added, ForwardPass, Prefilled

from sdk.quote_mod_sdk.strategies.strategy_constructor import StrategyConstructor
from sdk.quote_mod_sdk.self_prompt import EraseMode
import numpy as np

TState = TypeVar("TState", bound="FlowState")

# ------------------------ Flow Primitives ------------------------ #


class RouteKind(Enum):
    QUESTION = auto()
    MESSAGE = auto()
    SUMMARY = auto()
    OUTPUT = auto()
    TOOL = auto()
    NOOP = auto()


@dataclass
class FlowRoute(Generic[TState]):
    kind: RouteKind
    target: Any = None
    message: Optional[str] = None
    callback: Optional[Callable[[ActionBuilder, TState, Any], Any]] = None


RouteTarget = Any


@runtime_checkable
class FlowState(Protocol):
    request_id: str
    current_question: Optional["FlowQuestion"]
    pending_route: Optional[FlowRoute]
    answers: Dict[str, str]
    # Optional generic data bag
    data: Dict[str, Any]


RouteSpec = Union["FlowQuestion[TState]", Callable[[TState], RouteTarget]]


def route_question(question: "FlowQuestion[TState]") -> FlowRoute[TState]:
    return FlowRoute(kind=RouteKind.QUESTION, target=question)


def route_message(text: str) -> FlowRoute[TState]:
    return FlowRoute(kind=RouteKind.MESSAGE, message=text)


def route_output(text: str) -> FlowRoute[TState]:
    return FlowRoute(kind=RouteKind.OUTPUT, message=text)


def route_summary(message: Optional[str] = None) -> FlowRoute[TState]:
    return FlowRoute(kind=RouteKind.SUMMARY, message=message)


def route_noop() -> FlowRoute[TState]:
    return FlowRoute(kind=RouteKind.NOOP)


def route_tool(
    callback: Callable[[ActionBuilder, TState, Any], Any],
) -> FlowRoute[TState]:
    return FlowRoute(kind=RouteKind.TOOL, callback=callback)


def _coerce_route(target: RouteTarget) -> FlowRoute[TState]:
    if isinstance(target, FlowRoute):
        return target
    if isinstance(target, FlowQuestion):
        return route_question(target)
    if isinstance(target, FlowDefinition):
        return route_question(target.root)
    if callable(target):
        return FlowRoute(kind=RouteKind.TOOL, callback=target)
    if isinstance(target, str):
        return route_message(target)
    if target is None:
        return FlowRoute(kind=RouteKind.NOOP)
    raise ValueError(f"Unsupported route target: {target!r}")


@dataclass
class FlowQuestion(Generic[TState]):
    name: str
    """Name of the question. Answers to this flow will be stored here in the flow's state"""
    prompt: str
    """The self-prompt to generate"""
    strategy: StrategyConstructor
    completion_text: str = "\n"
    # New strategy-first config (preferred). If provided, takes precedence over responses/allowed_token_modes.
    erase_mode: Optional[EraseMode] = EraseMode.NONE
    assignments: List[Callable[[TState, str], None]] = field(default_factory=list)
    transitions: Dict[str, RouteSpec[TState]] = field(default_factory=dict)
    branch_resolvers: List[Callable[[TState], Optional[RouteSpec[TState]]]] = field(
        default_factory=list
    )
    default_route: Optional[RouteSpec[TState]] = None

    def on(self, answer: str, target: RouteSpec[TState]) -> "FlowQuestion[TState]":
        self.transitions[answer.lower()] = target
        return self

    def then(self, target: RouteSpec[TState]) -> "FlowQuestion[TState]":
        self.default_route = target
        return self

    def otherwise(self, target: RouteSpec[TState]) -> "FlowQuestion[TState]":
        self.default_route = target
        return self

    def assign(self, func: Callable[[TState, str], None]) -> "FlowQuestion[TState]":
        self.assignments.append(func)
        return self

    def branch(
        self, resolver: Callable[[TState], Optional[RouteSpec[TState]]]
    ) -> "FlowQuestion[TState]":
        self.branch_resolvers.append(resolver)
        return self

    def with_auto_answer(
        self, func: Callable[[TState], Optional[str]]
    ) -> "FlowQuestion[TState]":
        self.auto_answer_fn = func
        return self

    def resolve_route(
        self, state: TState, answer: Optional[str] = None
    ) -> Optional[FlowRoute[TState]]:
        spec: Optional[RouteSpec] = None
        if answer is not None:
            try:
                spec = self.transitions.get(answer.lower())
            except Exception:
                spec = None
        if spec is None:
            spec = self.default_route

        # If no explicit transition/default, allow branch resolvers to act as explicit transitions
        if spec is None and getattr(self, "branch_resolvers", None):
            for resolver in list(self.branch_resolvers):
                try:
                    rspec = resolver(state)
                except Exception:
                    continue
                if rspec is None:
                    continue
                while callable(rspec):
                    try:
                        rspec = rspec(state)
                    except Exception as e:
                        print("error when getting next route:", e, type(rspec))
                        break
                target = rspec
                if target is None:
                    continue
                return _coerce_route(target)
        if spec is None:
            return None

        while callable(spec):
            try:
                spec = spec(state)
            except Exception as e:
                print("error when getting next route:", e)
                raise e
        target = spec
        if target is None:
            return None
        return _coerce_route(target)


@dataclass
class FlowDefinition(Generic[TState]):
    name: str
    root: FlowQuestion[TState]
    summary_builder: Callable[[TState], str]

    def all_questions(self) -> List[FlowQuestion]:
        seen: set[int] = set()
        order: List[FlowQuestion] = []
        stack: List[FlowQuestion] = [self.root]
        while stack:
            node = stack.pop()
            node_id = id(node)
            if node_id in seen:
                continue
            seen.add(node_id)
            order.append(node)
            specs: List[RouteSpec] = list(node.transitions.values())
            if node.default_route is not None:
                specs.append(node.default_route)
            for spec in specs:
                try:
                    if isinstance(spec, FlowRoute):
                        route = spec
                    elif callable(spec):
                        # Use a minimal probe state for introspection
                        class _Probe:
                            request_id: str = "__introspect__"
                            current_question: Optional[FlowQuestion] = None
                            pending_route: Optional[FlowRoute] = None
                            answers: Dict[str, str] = {}
                            data: Dict[str, Any] = {}

                        route = _coerce_route(spec(_Probe()))
                    else:
                        route = _coerce_route(spec)
                except Exception:
                    continue
                if route.kind == RouteKind.QUESTION and isinstance(
                    route.target, FlowQuestion
                ):
                    stack.append(route.target)
        return order


@dataclass
class RequestState:
    request_id: str
    current_question: Optional[FlowQuestion] = None
    pending_route: Optional[FlowRoute] = None
    answers: Dict[str, str] = field(default_factory=dict)
    # Generic per-request data bag for domain state (user_id, reservation_id, etc.).
    data: Dict[str, Any] = field(default_factory=dict)


# ------------------------ Engine ------------------------ #


def _encode_text(tokenizer: Any, text: str) -> List[int]:
    if hasattr(tokenizer, "encode"):
        ids = tokenizer.encode(text, add_special_tokens=False)
    elif callable(tokenizer):
        ids = tokenizer(text)
    else:
        raise RuntimeError("Tokenizer does not support encode")
    assert isinstance(ids, list), "Tokenizer did not return a list"
    return [int(t) for t in ids]


def _decode_tokens(tokenizer: Any, tokens: List[int]) -> str:
    if hasattr(tokenizer, "decode"):
        return tokenizer.decode(tokens, skip_special_tokens=True)
    raise RuntimeError("Tokenizer does not support decode")


class FlowEngine(Generic[TState]):
    def __init__(
        self,
        *,
        entry_question: FlowQuestion[TState],
        flows: Optional[Dict[str, FlowDefinition[TState]]] = None,
        state_factory: Optional[Callable[[str], TState]] = None,
    ):
        # Single entry point to the flow graph; can branch via .on("A", ...), .on("B", ...)
        self.entry_question = entry_question
        self.flows = dict(flows) if flows else {}
        self._constraints: Dict[str, SelfPrompt] = {}
        self._states: Dict[str, TState] = {}
        self._state_factory: Callable[[str], TState] = state_factory or (
            lambda rid: cast(TState, RequestState(request_id=rid))
        )

    def _get_state(self, request_id: str) -> TState:
        st = self._states.get(request_id)
        if st is None:
            st = self._state_factory(request_id)
            self._states[request_id] = st
        return st

    def _ensure_constraint(self, question: FlowQuestion) -> SelfPrompt:
        helper = self._constraints.get(question.name)
        if helper is not None:
            return helper
        # Prefer explicit strategy if provided on the question

        print(
            f"[Flow] Build SelfPrompt for question={question.name} erase_mode={question.erase_mode} strategy={question.strategy}"
        )
        helper = SelfPrompt(
            prompt={"text": question.prompt},
            strategy=question.strategy,
            completion=question.completion_text,
            erase=question.erase_mode,
            mask_value=-1e9,
        )
        self._constraints[question.name] = helper
        return helper

    def _prepare_question_for_state(
        self, state: TState, question: FlowQuestion[TState]
    ) -> None:
        constraint = self._ensure_constraint(question)

    def _decode_answer(self, tokenizer: Any, tokens: List[int]) -> Optional[str]:
        if not tokens:
            return None
        try:
            text = _decode_tokens(tokenizer, tokens)
            return text if text else None
        except Exception:
            return None

    def _perform_route(
        self,
        event,
        state: TState,
        current_q: FlowQuestion[TState],
        route: FlowRoute[TState],
        actions: ActionBuilder,
        tokenizer: Any,
    ):
        if route.kind == RouteKind.QUESTION and isinstance(route.target, FlowQuestion):
            nq = route.target
            # Auto-advance if branch/auto-answer resolves immediately
            auto_route = self._resolve_auto_route(state, nq)
            if auto_route is not None:
                return self._perform_route(
                    event, state, current_q, auto_route, actions, tokenizer
                )
            state.current_question = nq
            self._prepare_question_for_state(state, nq)
            if isinstance(event, ForwardPass):
                constraint = self._ensure_constraint(nq)
                print(f"└»[Flow] ForwardPass switched to next question={nq.name}")
                return constraint.handle_forward_pass(event, actions, tokenizer)
            return actions.noop()

        if route.kind == RouteKind.MESSAGE:
            msg = route.message or ""
            from_text = msg
            toks = _encode_text(tokenizer, from_text)
            eos_id = getattr(tokenizer, "eos_token_id", None)
            if eos_id is not None:
                toks.append(int(eos_id))
                state.current_question = None
            return actions.force_tokens(toks)
        if route.kind == RouteKind.SUMMARY:
            summary = route.message or "Flow complete."
            for flow in self.flows.values():
                if current_q in flow.all_questions():
                    summary = flow.summary_builder(state)
                    break
            from_text = summary
            toks = _encode_text(tokenizer, from_text)
            eos_id = getattr(tokenizer, "eos_token_id", None)
            if eos_id is not None:
                toks.append(int(eos_id))
                state.current_question = None
            return actions.force_tokens(toks)
        if route.kind == RouteKind.TOOL and route.callback:
            try:
                return route.callback(actions, state, tokenizer)
            except Exception as e:
                print("error calling standard callback", e)
                route2 = _coerce_route(route.callback(state))
                return self._perform_route(
                    event, state, current_q, route2, actions, tokenizer
                )
        if route.kind == RouteKind.OUTPUT:
            return actions.force_output(
                tokenizer.encode(route.message, add_special_tokens=False)
            )
        return actions.noop()

    def _resolve_auto_route(
        self, state: TState, question: FlowQuestion[TState]
    ) -> Optional[FlowRoute[TState]]:
        # Only support auto-answer here; branches are evaluated on completion (resolve_route)
        # so they act like dynamic transitions after the question is answered.
        auto_fn = getattr(question, "auto_answer_fn", None)
        if callable(auto_fn):
            try:
                ans = auto_fn(state)
            except Exception:
                ans = None
            if isinstance(ans, str) and ans.strip():
                normalized = ans.strip()
                state.answers[question.name] = normalized
                for assign in question.assignments:
                    try:
                        assign(state, normalized)
                    except Exception:
                        pass
                route = question.resolve_route(state, normalized)
                if route is not None:
                    return route
        return None

    def _advance_on_completion(
        self,
        *,
        event,
        state: TState,
        question: FlowQuestion,
        last_action: Any,
        actions: ActionBuilder,
        tokenizer: Any,
        event_kind: str,
    ):
        """If the question's SPC is completed, resolve and perform the next route.

        - If completion occurs on FP and last_action is Backtrack, queue the route for the next FP and return the Backtrack.
        - Otherwise, perform the route immediately and return the route action.
        """
        constraint = self._ensure_constraint(question)
        rid = state.request_id
        cstate = constraint._states.get(rid)
        if cstate is None or not getattr(cstate, "completed", False):
            return last_action if last_action is not None else actions.noop()

        ans_tokens = list(getattr(cstate, "answer_tokens", []) or [])
        ans_text = self._decode_answer(tokenizer, ans_tokens)
        print(f'ANSWER: {question.name}: "{ans_text}"')
        if isinstance(ans_text, str):
            state.answers[question.name] = ans_text
        for assign in question.assignments:
            if ans_text:
                assign(state, ans_text)

        route = (
            question.resolve_route(state, ans_text)
            if isinstance(ans_text, str)
            else question.resolve_route(state, None)
        )

        if not route:
            return last_action if last_action is not None else actions.noop()

        # If the constraint completed by emitting a Backtrack (erase modes), queue the route
        # for the next ForwardPass so we don't "double-act" in one step.
        if isinstance(last_action, Backtrack):
            state.pending_route = route
            return last_action

        return self._perform_route(event, state, question, route, actions, tokenizer)

    def handle_event(self, event, actions: ActionBuilder, tokenizer: Any):
        request_id = getattr(event, "request_id", None)
        if not isinstance(request_id, str) or tokenizer is None:
            return actions.noop()

        state = self._get_state(request_id)

        if isinstance(event, Prefilled):
            # Prepare all constraints for this request
            entry_c = self._ensure_constraint(self.entry_question)
            entry_c.handle_prefilled(event, tokenizer)
            print(
                f"[Flow] Prefilled: entry_question={self.entry_question.name}, flows={list(self.flows.keys())}, req_id={request_id}"
            )
            # for flow in self.flows.values():
            #     for question in flow.all_questions():
            #         self._ensure_constraint(question).handle_prefilled(event, tokenizer)
            # Initialize at classifier

            state.current_question = self.entry_question
            self._prepare_question_for_state(state, self.entry_question)
            state.pending_route = None
            return actions.noop()

        if isinstance(event, ForwardPass):
            print(f"[Flow] Forward pass - {request_id}")



            q = state.current_question
            if q is None and state.pending_route is None:
                print("└»[Flow] No question")
                return actions.noop()
            # If a transition is queued from a prior completed FP (e.g., erase_mode backtrack), perform it now.
            if state.pending_route is not None:
                route = state.pending_route
                state.pending_route = None
                if route.kind == RouteKind.QUESTION and isinstance(
                    route.target, FlowQuestion
                ):
                    nq = route.target
                    state.current_question = nq
                    self._prepare_question_for_state(state, nq)
                    constraint = self._ensure_constraint(nq)
                    print(f"└»[Flow] ForwardPass switched to next question={nq.name}")
                    return constraint.handle_forward_pass(event, actions, tokenizer)
                if route.kind == RouteKind.MESSAGE:
                    msg = route.message or ""
                    from_text = msg
                    toks = _encode_text(tokenizer, from_text)
                    eos_id = getattr(tokenizer, "eos_token_id", None)
                    if eos_id is not None:
                        toks.append(int(eos_id))
                        state.current_question = None
                    print(f"└»[Flow] ForwardPass inject message len={len(toks)}")
                    return actions.force_tokens(toks)
                if route.kind == RouteKind.SUMMARY:
                    summary = route.message or "Flow complete."
                    for flow in self.flows.values():
                        if q in flow.all_questions():
                            summary = flow.summary_builder(state)
                            break
                    from_text = summary
                    toks = _encode_text(tokenizer, from_text)
                    eos_id = getattr(tokenizer, "eos_token_id", None)
                    if eos_id is not None:
                        toks.append(int(eos_id))
                        state.current_question = None
                    print(f"└»[Flow] ForwardPass inject summary len={len(toks)}")
                    return actions.force_tokens(toks)
                if route.kind == RouteKind.TOOL and route.callback:
                    print(
                        f"└»[Flow] ForwardPass invoke tool callback from question={q.name}"
                    )
                    return route.callback(actions, state, tokenizer)
                if route.kind == RouteKind.OUTPUT:
                    return actions.force_output(
                        tokenizer.encode(route.message, add_special_tokens=False)
                    )
                return actions.noop()

            # Default: let the active question's constraint handle the FP.

            constraint = self._ensure_constraint(q)

            print(f"[Flow] ForwardPass at question={q.name}")
            act = constraint.handle_forward_pass(event, actions, tokenizer)
            return self._advance_on_completion(
                event=event,
                state=state,
                question=q,
                last_action=act,
                actions=actions,
                tokenizer=tokenizer,
                event_kind="forward",
            )

        if isinstance(event, Added):
            q = state.current_question
            if q is None:
                return actions.noop()
            constraint = self._ensure_constraint(q)
            result = constraint.handle_added(event, actions, tokenizer)
            return self._advance_on_completion(
                event=event,
                state=state,
                question=q,
                last_action=result,
                actions=actions,
                tokenizer=tokenizer,
                event_kind="added",
            )

        return actions.noop()


__all__ = [
    "FlowQuestion",
    "FlowDefinition",
    "FlowRoute",
    "RouteKind",
    "route_question",
    "route_message",
    "route_summary",
    "route_tool",
    "route_noop",
    "FlowEngine",
    "RequestState",
]
