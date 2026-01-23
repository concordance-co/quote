from __future__ import annotations

import sys
import warnings
import os
from types import SimpleNamespace
from typing import Any
import asyncio
import pytest


def _restore_real_max_and_quote_modules() -> None:
    # Remove any stubbed 'max' modules installed by parent conftest so we can
    # import the real MAX stack for integration tests in this folder.
    for name in list(sys.modules.keys()):
        if name == "max" or name.startswith("max."):
            sys.modules.pop(name, None)

    # Drop stubbed quote text pipeline if present so we load the real module
    # from the repository (inference/src/quote/pipelines/text_gen_pipeline.py).
    sys.modules.pop("quote.pipelines.text_gen_pipeline", None)

    # Drop any stubbed dotenv module; some parent fixtures may have installed
    # a minimal stub that lacks dotenv_values/loaders. We want the real package.
    sys.modules.pop("dotenv", None)


_restore_real_max_and_quote_modules()


def pytest_configure(config: pytest.Config) -> None:
    # Register the 'integration' marker to avoid PytestUnknownMarkWarning.
    config.addinivalue_line(
        "markers", "integration: marks tests as integration (uses real model/runtime)"
    )

    # Silence noisy DeprecationWarnings from importlib during SWIG-backed imports
    warnings.filterwarnings(
        "ignore",
        message=r"builtin type SwigPy.* has no __module__ attribute",
        category=DeprecationWarning,
    )


@pytest.fixture(scope="module")
def real_model_env() -> SimpleNamespace:
    """Initialize and share the real model pipeline for mod-action tests.

    Provides:
      - mi: max.interfaces module
      - tokenizer: pipeline tokenizer
      - pipeline: initialized TextGenerationPipeline
      - model_id: resolved model string
      - format_prompt_from_messages: helper from quote.server.core
      - execute_impl: module for hot execute
      - new_context(request): helper to create a TextContext (handles event loop)
    """

    mi = pytest.importorskip("max.interfaces")
    try:
        from quote.server.core import init_pipeline, format_prompt_from_messages  # type: ignore
    except Exception as e:  # pragma: no cover - environment specific
        pytest.skip(f"Skipping integration tests; core import failed: {e}")

    # Use same default as servers
    model_id = os.environ.get("MODEL_ID", "modularai/Llama-3.1-8B-Instruct-GGUF")
    os.environ.setdefault("MAX_BATCH_SIZE", "15")
    try:
        tokenizer, pipeline, resolved = init_pipeline(model_id)
    except Exception as e:  # pragma: no cover - environment specific
        pytest.skip(f"Skipping integration tests; model init failed: {e}")

    # Ensure execute module is importable
    try:
        from quote.hot import execute_impl  # type: ignore
    except Exception as e:  # pragma: no cover - environment specific
        pytest.skip(f"Skipping integration tests; execute_impl import failed: {e}")

    # Helper for creating a new context (handles lack of running loop)
    def new_context(request: Any) -> Any:
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(tokenizer.new_context(request))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(tokenizer.new_context(request))
            finally:
                loop.close()

    # Ensure ModManager is wired to tokenizer
    try:
        mm = getattr(pipeline, "mod_manager", None)
        if mm is not None and hasattr(mm, "set_tokenizer"):
            mm.set_tokenizer(tokenizer)
    except Exception:
        pass

    return SimpleNamespace(
        mi=mi,
        tokenizer=tokenizer,
        pipeline=pipeline,
        model_id=resolved,
        format_prompt_from_messages=format_prompt_from_messages,
        execute_impl=execute_impl,
        new_context=new_context,
    )
    warnings.filterwarnings(
        "ignore",
        message=r"builtin type SwigPyObject has no __module__ attribute",
        category=DeprecationWarning,
    )
