from __future__ import annotations

import inspect
import textwrap
from typing import Any, Callable, Dict
from shared.types import ModAction, ModEvent  # type: ignore[attr-defined]


ModCallable = Callable[[ModEvent, Any | None], ModAction]


def serialize_mod(
    mod_fn: ModCallable, *, name: str | None = None, description: str | None = None
) -> Dict[str, Any]:
    """Serialize a mod callable into a payload that can be sent to the server."""
    module = inspect.getmodule(mod_fn)
    if module is None:
        raise ValueError("Mod callable must be defined in a module")
    try:
        source = inspect.getsource(module)
    except (OSError, TypeError) as exc:
        raise ValueError(
            f"Unable to extract source for module {module.__name__}"
        ) from exc

    payload: Dict[str, Any] = {
        "language": "python",
        "module": module.__name__,
        "entrypoint": mod_fn.__name__,
        "source": textwrap.dedent(source),
    }
    if name is not None:
        payload["name"] = name
    if description is not None:
        payload["description"] = description
    return payload


__all__ = ["serialize_mod"]
