from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import shutil
from threading import Lock
from typing import Iterable

from quote.backends.interface import ActivationConfig

from .schema import FeatureActivationRow, TABLE_ACTIVATION_FEATURES, create_indexes_sql, create_table_sql

logger = logging.getLogger(__name__)


class ActivationStore:
    def __init__(self, config: ActivationConfig) -> None:
        self._config = config
        self._db_path = Path(config.db_path)
        self._parquet_root = Path(config.parquet_path)
        self._lock = Lock()
        self._conn = None
        self._duckdb = None

    @property
    def enabled(self) -> bool:
        return bool(self._config.enabled)

    def setup(self) -> None:
        if not self.enabled:
            return
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._parquet_root.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        conn.execute(create_table_sql())
        for stmt in create_indexes_sql():
            conn.execute(stmt)

    def write_feature_rows(self, rows: Iterable[FeatureActivationRow]) -> int:
        if not self.enabled:
            return 0
        rows_list = list(rows)
        if not rows_list:
            return 0
        self.setup()
        payload = [asdict(row) for row in rows_list]

        with self._lock:
            conn = self._get_conn()
            conn.executemany(
                f"""
                INSERT INTO {TABLE_ACTIVATION_FEATURES} (
                    request_id, step, token_position, token_id, created_at,
                    sae_release, sae_layer, feature_id, activation_value, rank,
                    source_mode, model_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        p["request_id"],
                        p["step"],
                        p["token_position"],
                        p["token_id"],
                        p["created_at"],
                        p["sae_release"],
                        p["sae_layer"],
                        p["feature_id"],
                        p["activation_value"],
                        p["rank"],
                        p["source_mode"],
                        p["model_id"],
                    )
                    for p in payload
                ],
            )

        # Best-effort parquet dataset write; analytics still work if this fails.
        try:
            self._write_parquet_dataset(payload)
        except Exception:
            logger.exception("Failed to write activation parquet rows")
        return len(rows_list)

    def cleanup_old_rows(self) -> int:
        if not self.enabled:
            return 0
        self.setup()
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(0, self._config.retention_days))
        with self._lock:
            conn = self._get_conn()
            before = conn.execute(f"SELECT COUNT(*) FROM {TABLE_ACTIVATION_FEATURES}").fetchone()
            conn.execute(
                f"DELETE FROM {TABLE_ACTIVATION_FEATURES} WHERE created_at < ?",
                [cutoff.isoformat()],
            )
            after = conn.execute(f"SELECT COUNT(*) FROM {TABLE_ACTIVATION_FEATURES}").fetchone()
        self._cleanup_old_parquet_partitions(cutoff.date().isoformat())
        if not before or not after:
            return 0
        return max(0, int(before[0]) - int(after[0]))

    def count_rows(self) -> int:
        if not self.enabled:
            return 0
        self.setup()
        conn = self._get_conn()
        val = conn.execute(f"SELECT COUNT(*) FROM {TABLE_ACTIVATION_FEATURES}").fetchone()
        if not val:
            return 0
        return int(val[0])

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn = None

    def _get_conn(self):
        if self._conn is not None:
            return self._conn
        try:
            import duckdb
        except Exception as e:
            raise RuntimeError("duckdb is required for activation storage") from e
        self._duckdb = duckdb
        self._conn = duckdb.connect(str(self._db_path))
        return self._conn

    def _write_parquet_dataset(self, rows: list[dict]) -> None:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except Exception:
            # duckdb table remains authoritative when pyarrow isn't installed.
            return

        for row in rows:
            row["event_date"] = str(row["created_at"])[:10]
        table = pa.Table.from_pylist(rows)
        pq.write_to_dataset(table, root_path=str(self._parquet_root), partition_cols=["event_date"])

    def _cleanup_old_parquet_partitions(self, cutoff_date: str) -> None:
        if not self._parquet_root.exists():
            return
        for child in self._parquet_root.iterdir():
            if not child.is_dir():
                continue
            name = child.name
            if not name.startswith("event_date="):
                continue
            date_val = name.split("=", 1)[1]
            if date_val < cutoff_date:
                shutil.rmtree(child, ignore_errors=True)
