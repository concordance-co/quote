from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENGINE_ROOT = PROJECT_ROOT
INFERENCE_SRC = PROJECT_ROOT / "inference" / "src"
SDK_SRC = PROJECT_ROOT / "sdk"
SHARED_SRC = PROJECT_ROOT / "shared" / "src"

for p in (ENGINE_ROOT, INFERENCE_SRC, SDK_SRC, SHARED_SRC):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


def pytest_ignore_collect(collection_path, config):  # pragma: no cover
    """Prevent pytest from collecting mod "fixture" files as tests.

    `tests/mod_unit_tests/<event_type>/test_*.py` files are loaded dynamically by
    `tests/mod_unit_tests/test_mods.py`. If pytest collects them directly, it
    tries to execute the @mod-decorated functions as normal tests (missing the
    synthetic `event`/`actions` fixtures) and fails.
    """
    try:
        p = Path(str(collection_path))
    except Exception:
        return False

    parts = set(p.parts)
    if "tests" not in parts or "mod_unit_tests" not in parts:
        return False

    if p.suffix != ".py" or not p.name.startswith("test_"):
        return False

    if p.parent.name in {"added", "prefilled", "forward_pass", "sampled"}:
        return True
    return False
