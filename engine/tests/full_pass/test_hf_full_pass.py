from __future__ import annotations

import os
from typing import Iterator
from uuid import uuid4

import pytest

from quote.activations import ActivationQueries, ActivationStore
from quote.activations.schema import TABLE_ACTIVATION_FEATURES
from quote.backends.huggingface import HuggingFaceBackend
from quote.backends.interface import ActivationConfig, BackendConfig, GenerationConfig, SAEConfig
from quote.features.sae_extract import MinimalSAEExtractor
from quote.generation import generate
from quote.mods.manager import ModManager
from shared.types import ForceOutput, ForceTokens, Noop, Prefilled

pytestmark = [pytest.mark.integration]


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _new_request_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _encode_prompt(tokenizer, prompt: str) -> list[int]:
    messages = [
        {"role": "system", "content": "You are concise."},
        {"role": "user", "content": prompt},
    ]
    if hasattr(tokenizer, "apply_chat_template"):
        try:
            ids = tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
            )
            if isinstance(ids, list) and ids:
                return [int(t) for t in ids]
        except Exception:
            pass
    return [int(t) for t in tokenizer.encode(prompt, add_special_tokens=True)]


def _deterministic_cfg(max_tokens: int) -> GenerationConfig:
    return GenerationConfig(max_tokens=max_tokens, temperature=0.0, top_p=1.0, top_k=1)


@pytest.fixture(scope="session")
def fullpass_model_id() -> str:
    return (
        os.getenv("QUOTE_FULLPASS_MODEL")
        or os.getenv("CONCORDANCE_MODEL")
        or "meta-llama/Llama-3.1-8B-Instruct"
    )


@pytest.fixture(scope="session")
def fullpass_backend(fullpass_model_id: str) -> Iterator[HuggingFaceBackend]:
    cfg = BackendConfig(
        backend_type="huggingface",
        model_id=fullpass_model_id,
        device=os.getenv("QUOTE_FULLPASS_DEVICE", "auto"),
        hidden_state_layer=int(os.getenv("QUOTE_FULLPASS_LAYER", "16")),
        dtype=os.getenv("QUOTE_FULLPASS_DTYPE", "auto"),
        extract_attention=_env_bool("QUOTE_FULLPASS_EXTRACT_ATTENTION", False),
    )
    backend = HuggingFaceBackend(cfg)
    try:
        backend.load_model(fullpass_model_id, cfg)
    except Exception as exc:
        pytest.fail(f"Failed to load full-pass model {fullpass_model_id!r}: {exc}")
    try:
        yield backend
    finally:
        backend.shutdown()


@pytest.mark.fullpass
def test_hf_full_pass_smoke(fullpass_backend: HuggingFaceBackend) -> None:
    tokenizer = fullpass_backend.tokenizer()
    input_ids = _encode_prompt(tokenizer, "Give me one short sentence about testing.")
    result = generate(
        backend=fullpass_backend,
        input_ids=input_ids,
        request_id=_new_request_id("fp-smoke"),
        mod_manager=ModManager([], tokenizer=tokenizer),
        config=_deterministic_cfg(max_tokens=8),
    )

    assert len(result.output_ids) >= 1
    assert isinstance(result.output_text, str)
    event_types = {type(e).__name__ for e in result.events}
    assert {"Prefilled", "ForwardPass", "Added"}.issubset(event_types)
    assert int(result.metadata.get("steps_executed", 0)) >= 1


@pytest.mark.fullpass
def test_hf_full_pass_force_tokens_prefix(fullpass_backend: HuggingFaceBackend) -> None:
    tokenizer = fullpass_backend.tokenizer()
    forced_ids = tokenizer.encode("FORCED_PREFIX:", add_special_tokens=False)
    assert forced_ids, "Expected FORCE prefix text to produce at least one token"

    def mod(event, _tok):
        if isinstance(event, Prefilled):
            return ForceTokens(forced_ids)
        return Noop()

    result = generate(
        backend=fullpass_backend,
        input_ids=_encode_prompt(tokenizer, "Write exactly one short line."),
        request_id=_new_request_id("fp-force-tokens"),
        mod_manager=ModManager([mod], tokenizer=tokenizer),
        config=_deterministic_cfg(max_tokens=max(8, len(forced_ids) + 2)),
    )
    assert result.output_ids[: len(forced_ids)] == [int(t) for t in forced_ids]
    assert len(result.output_ids) >= len(forced_ids)


@pytest.mark.fullpass
def test_hf_full_pass_force_output_terminal(fullpass_backend: HuggingFaceBackend) -> None:
    tokenizer = fullpass_backend.tokenizer()
    forced_ids = tokenizer.encode("FULL_PASS_OK", add_special_tokens=False)
    assert forced_ids, "Expected FORCE output text to produce at least one token"

    def mod(event, _tok):
        if isinstance(event, Prefilled):
            return ForceOutput(forced_ids)
        return Noop()

    result = generate(
        backend=fullpass_backend,
        input_ids=_encode_prompt(tokenizer, "Ignore this and do what the mod says."),
        request_id=_new_request_id("fp-force-output"),
        mod_manager=ModManager([mod], tokenizer=tokenizer),
        config=_deterministic_cfg(max_tokens=16),
    )
    assert result.output_ids == [int(t) for t in forced_ids]
    assert result.metadata.get("terminal_action") == "ForceOutput"


@pytest.mark.fullpass_sae
def test_hf_full_pass_inline_sae_writes_activation_rows(
    fullpass_backend: HuggingFaceBackend, tmp_path
) -> None:
    if not _env_bool("QUOTE_FULLPASS_ENABLE_SAE", False):
        pytest.skip("Set QUOTE_FULLPASS_ENABLE_SAE=1 to run inline SAE full-pass test.")

    sae_cfg = SAEConfig(
        enabled=True,
        mode="inline",
        sae_id=os.getenv("QUOTE_FULLPASS_SAE_ID", "llama_scope_lxr_8x"),
        layer=int(os.getenv("QUOTE_FULLPASS_SAE_LAYER", os.getenv("QUOTE_FULLPASS_LAYER", "16"))),
        top_k=int(os.getenv("QUOTE_FULLPASS_SAE_TOP_K", "8")),
        sae_local_path=(
            os.getenv("QUOTE_FULLPASS_SAE_LOCAL_PATH")
            or os.getenv("CONCORDANCE_SAE_LOCAL_PATH")
        ),
    )
    extractor = MinimalSAEExtractor(sae_cfg)
    try:
        loaded = extractor._ensure_loaded()  # noqa: SLF001 - explicit preflight for integration test
    except Exception as exc:
        pytest.fail(f"SAE preflight failed for release={sae_cfg.sae_id!r}: {exc}")
    if loaded is None:
        pytest.skip("SAE extractor unavailable in this environment.")

    activation_cfg = ActivationConfig(
        enabled=True,
        db_path=str(tmp_path / "full_pass_activations.duckdb"),
        parquet_path=str(tmp_path / "parquet"),
        retention_days=7,
    )
    store = ActivationStore(activation_cfg)
    store.setup()

    tokenizer = fullpass_backend.tokenizer()
    request_id = _new_request_id("fp-sae")
    result = generate(
        backend=fullpass_backend,
        input_ids=_encode_prompt(tokenizer, "List two concise facts about ducks."),
        request_id=request_id,
        mod_manager=ModManager([], tokenizer=tokenizer),
        config=_deterministic_cfg(max_tokens=6),
        activation_store=store,
        sae_extractor=extractor,
    )
    assert len(result.output_ids) >= 1
    assert store.count_rows() > 0

    conn = store._get_conn()  # noqa: SLF001 - integration assertion on persisted rows
    row = conn.execute(
        f"""
        SELECT feature_id, source_mode
        FROM {TABLE_ACTIVATION_FEATURES}
        WHERE request_id = ?
        ORDER BY step ASC, token_position ASC, rank ASC
        LIMIT 1
        """,
        [request_id],
    ).fetchone()
    assert row is not None
    feature_id = int(row[0])
    assert str(row[1]) == "inline"

    queries = ActivationQueries(activation_cfg)
    try:
        timeline = queries.feature_deltas_over_time(
            request_id,
            feature_id,
            sae_layer=sae_cfg.layer,
            limit=128,
        )
    finally:
        queries.close()
        store.close()
    assert len(timeline) >= 1
