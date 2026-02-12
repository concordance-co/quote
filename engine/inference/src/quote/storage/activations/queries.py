from __future__ import annotations

from typing import Any

from quote.backends.interface import ActivationConfig

from .schema import TABLE_ACTIVATION_FEATURES
from .store import ActivationStore


class ActivationQueries:
    def __init__(self, config: ActivationConfig) -> None:
        self._store = ActivationStore(config)
        self._store.setup()

    def feature_deltas_over_time(
        self,
        request_id: str,
        feature_id: int,
        *,
        sae_layer: int | None = None,
        limit: int = 512,
    ) -> list[dict[str, Any]]:
        conn = self._store._get_conn()
        where = ["request_id = ?", "feature_id = ?"]
        params: list[Any] = [request_id, int(feature_id)]
        if sae_layer is not None:
            where.append("sae_layer = ?")
            params.append(int(sae_layer))
        params.append(int(limit))
        rows = conn.execute(
            f"""
            SELECT
                step,
                token_position,
                token_id,
                activation_value,
                activation_value - LAG(activation_value)
                    OVER (ORDER BY step ASC, token_position ASC) AS delta
            FROM {TABLE_ACTIVATION_FEATURES}
            WHERE {" AND ".join(where)}
            ORDER BY step ASC, token_position ASC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [
            {
                "step": int(r[0]),
                "token_position": int(r[1]),
                "token_id": int(r[2]) if r[2] is not None else None,
                "activation_value": float(r[3]),
                "delta": float(r[4]) if r[4] is not None else None,
            }
            for r in rows
        ]

    def search_feature_threshold(
        self,
        feature_id: int,
        min_activation: float,
        *,
        sae_layer: int | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        conn = self._store._get_conn()
        where = ["feature_id = ?", "activation_value >= ?"]
        params: list[Any] = [int(feature_id), float(min_activation)]
        if sae_layer is not None:
            where.append("sae_layer = ?")
            params.append(int(sae_layer))
        params.append(int(limit))
        rows = conn.execute(
            f"""
            SELECT
                request_id,
                step,
                token_position,
                token_id,
                activation_value,
                sae_release,
                sae_layer,
                model_id,
                created_at
            FROM {TABLE_ACTIVATION_FEATURES}
            WHERE {" AND ".join(where)}
            ORDER BY activation_value DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [
            {
                "request_id": str(r[0]),
                "step": int(r[1]),
                "token_position": int(r[2]),
                "token_id": int(r[3]) if r[3] is not None else None,
                "activation_value": float(r[4]),
                "sae_release": str(r[5]),
                "sae_layer": int(r[6]),
                "model_id": str(r[7]),
                "created_at": str(r[8]),
            }
            for r in rows
        ]

    def close(self) -> None:
        self._store.close()
