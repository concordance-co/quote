from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


class NeuronpediaClient:
    """Best-effort metadata lookup for SAE features."""

    def __init__(self, base_url: str = "https://www.neuronpedia.org", timeout: float = 8.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)

    def lookup_feature(self, *, sae_release: str, layer: int, feature_id: int) -> dict[str, Any] | None:
        # Endpoint compatibility may vary; this wrapper intentionally degrades gracefully.
        url = (
            f"{self.base_url}/api/feature?"
            f"sae={sae_release}&layer={int(layer)}&feature={int(feature_id)}"
        )
        try:
            resp = requests.get(url, timeout=self.timeout)
            if not resp.ok:
                return None
            payload = resp.json()
            if not isinstance(payload, dict):
                return None
            return payload
        except Exception:
            logger.debug("Neuronpedia feature lookup failed", exc_info=True)
            return None

