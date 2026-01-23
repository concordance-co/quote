from typing import Optional, List, Protocol, Any, runtime_checkable

from .base import Strategy, tokenize_str, TrieNode
from .list_strategy import ListStrategy
from .primitives import (
    UntilStrategy,
    CharsStrategy,
    ChoicesStrategy,
    UntilEndType,
    CharsMode,
)


@runtime_checkable
class StrategyConstructor(Protocol):
    def into_strategy(self, tokenizer: Any) -> Strategy: ...


class ListStrat(StrategyConstructor):
    open: Optional[str] = None
    """What to start the list with. i.e. if generating json it would be  \"[\""""
    close: Optional[str] = None
    """What to end the list with. i.e. if generating json it would be  \"]\""""
    wrap: Optional[str] = None
    """What to wrap each element with. i.e. a string you would want to wrap with \""""
    sep: str = ", "
    """What to separate each element with. By default it is \", \""""
    min: Optional[int] = None
    """Minimum number of elements to generate. By default it is 0"""
    max: Optional[int] = None
    """Maximum number of elements to generate. By default it is None, letting the LLM decide when to close the list"""
    end_with: Optional[str] = None
    """After closing the list, the string to end constrained generation with."""
    elements: List[StrategyConstructor] | StrategyConstructor = []
    """Either a list of or a single strategy constructor. If a list, assumes min and max equal to the list. For example,
    [ChoicesStrategy(["a", "b"]), ChoicesStrategy(["c", "d"]), ChoicesStrategy(["e", "f"])] => will *always* generate: ["a"/"b", "c"/"d", "e"/"f"]
    and ignore min/max
    """

    def __init__(
        self,
        elements: List[StrategyConstructor] | StrategyConstructor,
        open: Optional[str] = None,
        close: Optional[str] = None,
        wrap: Optional[str] = None,
        sep: Optional[str] = None,
        min: Optional[int] = None,
        max: Optional[int] = None,
        end_with: Optional[str] = None,
    ):
        """

        Args:
            `open`: What to start the list with. i.e. if generating json it would be  \"[\"
            `close`: What to end the list with. i.e. if generating json it would be  \"]\"
            `wrap`: What to wrap each element with. i.e. a string you would want to wrap with \"
            `sep`: What to separate each element with. By default it is \", \"
            `min`: Minimum number of elements to generate. By default it is 0
            `max`: Maximum number of elements to generate. By default it is None, letting the LLM decide when to close the list
            `end_with`: After closing the list, the string to end constrained generation with
            `elements`: Either a list of or a single strategy constructor. If a list, assumes min and max equal to the list. For example,
            [ChoicesStrategy(["a", "b"]), ChoicesStrategy(["c", "d"]), ChoicesStrategy(["e", "f"])] => will *always* generate: ["a"/"b", "c"/"d", "e"/"f"]
            and ignore min/max
        """
        if open:
            self.open = open
        if close:
            self.close = close
        if wrap:
            self.wrap = wrap
        if sep:
            self.sep = sep
        if min:
            self.min = min
        if max:
            self.max = max
        if end_with:
            self.end_with = end_with
        self.elements = elements
        if isinstance(elements, list):
            self.min = len(elements)
            self.max = len(elements)

    def into_strategy(self, tokenizer: Any) -> Strategy:
        open_ids = tokenize_str(self.open, tokenizer)
        close_ids = tokenize_str(self.close, tokenizer)
        wrap_ids = tokenize_str(self.wrap, tokenizer)
        sep_ids = tokenize_str(self.sep, tokenizer)
        end_with_ids = tokenize_str(self.end_with, tokenizer)
        min_e = int(self.min or 0)
        max_val = self.max
        max_e = int(max_val) if isinstance(max_val, (int, float)) else None
        elements = self.elements
        if isinstance(elements, list):
            elements = [e.into_strategy(tokenizer) for e in elements]
        else:
            elements = elements.into_strategy(tokenizer)

        return ListStrategy(
            open_ids=open_ids,
            close_ids=close_ids,
            wrap_ids=wrap_ids,
            sep_ids=sep_ids,
            end_with_ids=end_with_ids,
            min_elements=min_e,
            max_elements=max_e,
            elements=elements,
        )


class CharsStrat(StrategyConstructor):
    mode: CharsMode
    """The allowed character type mode. One of: ALPHA, ALPHANUMERIC, NUMERIC, STRING"""
    min: Optional[int] = None
    """Minimum number of characters to generate. By default it is 0"""
    stop: int | str
    """Either the maximum number of characters to generate or a stop character"""

    def __init__(self, mode: CharsMode, stop: int | str, **kwargs):
        if kwargs.get("min"):
            self.min = kwargs.get("min")
        self.mode = mode
        self.stop = stop

    def into_strategy(self, tokenizer: Any) -> Strategy:
        return CharsStrategy(self.mode, self.stop, self.min or 0)


class UntilStrat(StrategyConstructor):
    end_type: UntilEndType
    """One of: TAG, ANYCHAR - ends on either a sequence (tag) or when it sees any character listed"""
    end: str
    """
    Generate until `end` str is produced. If end_type is ANY_CHAR, as soon as any of the characters in this string are seen, constrained generation ends.
    If end_type is TAG, wait until the entire tag is produced.
    """
    start: Optional[str] = None
    """Force the LLM to generate a starting sequence. Useful for if the user is backtracking the prompt away."""

    def __init__(self, start: str, end_type: UntilEndType, end: str):
        self.end_type = end_type
        self.end = end
        self.start = start

    def into_strategy(self, tokenizer: Any) -> Strategy:
        return UntilStrategy(self.start, self.end_type, self.end)


class ChoicesStrat(StrategyConstructor):
    choices: List[str]
    """List of strings the generator must choose from. The strings can be multiple tokens long - the generator will
    construct a trie of allowed tokens and iterate through them. i.e.:
        1. ["hello", "hello_world"]
        2. can only select "hello" token on first iteration
        3. can either select to end constrained generation or "_world" token
    """

    def __init__(self, choices: List[str]):
        self.choices = choices

    def into_strategy(self, tokenizer: Any) -> Strategy:
        root = TrieNode()
        seen = set()
        for text in self.choices:
            ids = tokenizer.encode(text, add_special_tokens=False)
            seq = [int(t) for t in (list(ids) if not isinstance(ids, list) else ids)]
            key = tuple(seq)
            if key and key not in seen:
                seen.add(key)
                root.insert(list(seq))
        return ChoicesStrategy(root)
