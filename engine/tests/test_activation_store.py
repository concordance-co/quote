from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

pytestmark = [pytest.mark.unit]


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INFERENCE_SRC = PROJECT_ROOT / "inference" / "src"
if str(INFERENCE_SRC) not in sys.path:
    sys.path.insert(0, str(INFERENCE_SRC))


from quote.storage.activations import ActivationQueries, ActivationStore, FeatureActivationRow
from quote.backends.interface import ActivationConfig


def _cfg(tmp_path: Path, retention_days: int = 14) -> ActivationConfig:
    return ActivationConfig(
        enabled=True,
        db_path=str(tmp_path / "activations.duckdb"),
        parquet_path=str(tmp_path / "parquet"),
        retention_days=retention_days,
    )


def test_activation_store_write_and_count(tmp_path: Path) -> None:
    store = ActivationStore(_cfg(tmp_path))
    store.setup()

    rows = [
        FeatureActivationRow.new(
            request_id="r1",
            step=0,
            token_position=0,
            token_id=101,
            sae_release="llama_scope_lxr_8x",
            sae_layer=16,
            feature_id=42,
            activation_value=0.11,
            rank=1,
            source_mode="nearline",
            model_id="meta-llama/Llama-3.1-8B-Instruct",
        ),
        FeatureActivationRow.new(
            request_id="r1",
            step=1,
            token_position=1,
            token_id=202,
            sae_release="llama_scope_lxr_8x",
            sae_layer=16,
            feature_id=42,
            activation_value=0.37,
            rank=1,
            source_mode="nearline",
            model_id="meta-llama/Llama-3.1-8B-Instruct",
        ),
    ]
    inserted = store.write_feature_rows(rows)
    assert inserted == 2
    assert store.count_rows() == 2


def test_feature_delta_query(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    store = ActivationStore(cfg)
    store.setup()
    store.write_feature_rows(
        [
            FeatureActivationRow.new(
                request_id="r2",
                step=0,
                token_position=0,
                token_id=1,
                sae_release="llama_scope_lxr_8x",
                sae_layer=16,
                feature_id=7,
                activation_value=0.2,
                rank=1,
                source_mode="nearline",
                model_id="m",
            ),
            FeatureActivationRow.new(
                request_id="r2",
                step=1,
                token_position=1,
                token_id=2,
                sae_release="llama_scope_lxr_8x",
                sae_layer=16,
                feature_id=7,
                activation_value=0.5,
                rank=1,
                source_mode="nearline",
                model_id="m",
            ),
        ]
    )

    q = ActivationQueries(cfg)
    rows = q.feature_deltas_over_time("r2", 7)
    assert len(rows) == 2
    assert rows[0]["delta"] is None
    assert pytest.approx(rows[1]["delta"], rel=1e-6) == 0.3


def test_retention_cleanup(tmp_path: Path) -> None:
    store = ActivationStore(_cfg(tmp_path, retention_days=0))
    store.setup()
    old_ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    recent_ts = datetime.now(timezone.utc).isoformat()
    old_row = FeatureActivationRow(
        request_id="r3",
        step=0,
        token_position=0,
        token_id=11,
        created_at=old_ts,
        sae_release="llama_scope_lxr_8x",
        sae_layer=16,
        feature_id=9,
        activation_value=0.2,
        rank=1,
        source_mode="nearline",
        model_id="m",
    )
    new_row = FeatureActivationRow(
        request_id="r3",
        step=1,
        token_position=1,
        token_id=12,
        created_at=recent_ts,
        sae_release="llama_scope_lxr_8x",
        sae_layer=16,
        feature_id=9,
        activation_value=0.4,
        rank=1,
        source_mode="nearline",
        model_id="m",
    )
    store.write_feature_rows([old_row, new_row])
    deleted = store.cleanup_old_rows()
    assert deleted >= 1
    assert store.count_rows() <= 1
