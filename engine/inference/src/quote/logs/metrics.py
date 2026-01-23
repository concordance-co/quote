from __future__ import annotations

from typing import Dict, Iterable

import numpy as np


def get_last_step_logits_rows(logits_obj, batch_indices: Iterable[int]) -> Dict[int, np.ndarray]:
    """
    Return a mapping of batch index -> 1D numpy array of raw logits for the last time step.

    Accepts either a numpy array or an object exposing `.to_numpy()`.
    Handles shapes:
      - (B, V)
      - (B, T, V)  (takes last T)
      - Any higher dims treated like (..., V) and last vector is used per batch.
    Fails soft (omits entries) if shapes are unexpected.
    """
    try:
        if hasattr(logits_obj, "to_numpy"):
            arr = logits_obj.to_numpy()
        else:
            arr = np.asarray(logits_obj)
    except Exception:
        return {}

    rows: Dict[int, np.ndarray] = {}
    try:
        if arr.ndim == 2:
            # (B, V)
            for bidx in batch_indices:
                try:
                    rows[int(bidx)] = np.array(arr[int(bidx)], copy=False)
                except Exception:
                    continue
        elif arr.ndim >= 3:
            # (B, T, V, ...), use last along time dim and squeeze extras to 1D if possible
            for bidx in batch_indices:
                try:
                    vec = arr[int(bidx)]
                    # take last along first non-batch axis
                    vec = vec.reshape(vec.shape[0], -1)[-1]
                    rows[int(bidx)] = np.array(vec, copy=False)
                except Exception:
                    continue
    except Exception:
        return {}
    return rows


__all__ = ["get_last_step_logits_rows"]
