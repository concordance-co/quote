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

    def rows_for_request(
        self,
        request_id: str,
        *,
        feature_id: int | None = None,
        sae_layer: int | None = None,
        token_start: int | None = None,
        token_end: int | None = None,
        rank_max: int | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        conn = self._store._get_conn()
        where = ["request_id = ?"]
        params: list[Any] = [request_id]

        if feature_id is not None:
            where.append("feature_id = ?")
            params.append(int(feature_id))
        if sae_layer is not None:
            where.append("sae_layer = ?")
            params.append(int(sae_layer))
        if token_start is not None:
            where.append("token_position >= ?")
            params.append(int(token_start))
        if token_end is not None:
            where.append("token_position <= ?")
            params.append(int(token_end))
        if rank_max is not None:
            where.append("rank <= ?")
            params.append(int(rank_max))

        params.append(int(limit))
        rows = conn.execute(
            f"""
            SELECT
                step,
                token_position,
                token_id,
                feature_id,
                activation_value,
                rank,
                source_mode,
                sae_release,
                sae_layer,
                model_id,
                created_at
            FROM {TABLE_ACTIVATION_FEATURES}
            WHERE {" AND ".join(where)}
            ORDER BY step ASC, token_position ASC, rank ASC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [
            {
                "step": int(r[0]),
                "token_position": int(r[1]),
                "token_id": int(r[2]) if r[2] is not None else None,
                "feature_id": int(r[3]),
                "activation_value": float(r[4]),
                "rank": int(r[5]),
                "source_mode": str(r[6]),
                "sae_release": str(r[7]),
                "sae_layer": int(r[8]),
                "model_id": str(r[9]),
                "created_at": str(r[10]),
            }
            for r in rows
        ]

    def top_features_for_request(
        self,
        request_id: str,
        *,
        n: int = 50,
        sae_layer: int | None = None,
    ) -> list[dict[str, Any]]:
        conn = self._store._get_conn()
        where = ["request_id = ?"]
        params: list[Any] = [request_id]
        if sae_layer is not None:
            where.append("sae_layer = ?")
            params.append(int(sae_layer))
        params.append(int(n))
        rows = conn.execute(
            f"""
            SELECT
                feature_id,
                COUNT(*) AS hits,
                MAX(activation_value) AS max_activation,
                AVG(activation_value) AS avg_activation,
                MIN(sae_release) AS sae_release,
                MIN(sae_layer) AS sae_layer
            FROM {TABLE_ACTIVATION_FEATURES}
            WHERE {" AND ".join(where)}
            GROUP BY feature_id
            ORDER BY max_activation DESC, hits DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [
            {
                "feature_id": int(r[0]),
                "hits": int(r[1]),
                "max_activation": float(r[2]),
                "avg_activation": float(r[3]),
                "sae_release": str(r[4]),
                "sae_layer": int(r[5]),
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
