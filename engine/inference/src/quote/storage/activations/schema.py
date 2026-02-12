from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


TABLE_ACTIVATION_FEATURES = "activation_features_v1"


@dataclass
class FeatureActivationRow:
    request_id: str
    step: int
    token_position: int
    token_id: int | None
    created_at: str
    sae_release: str
    sae_layer: int
    feature_id: int
    activation_value: float
    rank: int
    source_mode: str
    model_id: str

    @classmethod
    def new(
        cls,
        *,
        request_id: str,
        step: int,
        token_position: int,
        token_id: int | None,
        sae_release: str,
        sae_layer: int,
        feature_id: int,
        activation_value: float,
        rank: int,
        source_mode: str,
        model_id: str,
    ) -> "FeatureActivationRow":
        return cls(
            request_id=request_id,
            step=int(step),
            token_position=int(token_position),
            token_id=int(token_id) if token_id is not None else None,
            created_at=datetime.now(timezone.utc).isoformat(),
            sae_release=str(sae_release),
            sae_layer=int(sae_layer),
            feature_id=int(feature_id),
            activation_value=float(activation_value),
            rank=int(rank),
            source_mode=str(source_mode),
            model_id=str(model_id),
        )

    def asdict(self) -> dict[str, Any]:
        return asdict(self)


def create_table_sql() -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {TABLE_ACTIVATION_FEATURES} (
        request_id TEXT NOT NULL,
        step INTEGER NOT NULL,
        token_position INTEGER NOT NULL,
        token_id INTEGER,
        created_at TIMESTAMPTZ NOT NULL,
        sae_release TEXT NOT NULL,
        sae_layer INTEGER NOT NULL,
        feature_id INTEGER NOT NULL,
        activation_value DOUBLE NOT NULL,
        rank INTEGER NOT NULL,
        source_mode TEXT NOT NULL,
        model_id TEXT NOT NULL
    );
    """


def create_indexes_sql() -> list[str]:
    return [
        f"CREATE INDEX IF NOT EXISTS idx_af_req_step ON {TABLE_ACTIVATION_FEATURES}(request_id, step);",
        f"CREATE INDEX IF NOT EXISTS idx_af_feature ON {TABLE_ACTIVATION_FEATURES}(feature_id);",
        f"CREATE INDEX IF NOT EXISTS idx_af_created_at ON {TABLE_ACTIVATION_FEATURES}(created_at);",
    ]

