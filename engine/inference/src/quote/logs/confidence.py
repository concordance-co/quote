from __future__ import annotations

import math
from typing import Iterable, Optional

import numpy as np


def logsumexp(x: np.ndarray) -> float:
    """
    Stable log-sum-exp for 1D arrays.
    """
    arr = np.asarray(x, dtype=np.float64)
    if arr.ndim != 1:
        arr = arr.reshape(-1)
    if arr.size == 0:
        return float("-inf")
    m = float(np.max(arr))
    # Avoid overflow in exp; if m is -inf handle gracefully
    if not math.isfinite(m):
        return m
    s = float(np.sum(np.exp(arr - m)))
    return float(m + math.log(s))


def selected_token_prob(logits_row: np.ndarray, token_id: int) -> float:
    """
    Compute p(token_id) from the raw model logits row via softmax.

    Returns a Python float in [0,1]. Raises ValueError on invalid input.
    """
    row = np.asarray(logits_row, dtype=np.float64)
    if row.ndim != 1:
        row = row.reshape(-1)
    if token_id < 0 or token_id >= row.size:
        raise ValueError(f"token_id {token_id} out of bounds for logits row of size {row.size}")
    lse = logsumexp(row)
    if not math.isfinite(lse):  # all -inf case
        return 0.0
    val = float(math.exp(float(row[int(token_id)]) - lse))
    # Numerical guard
    if val < 0.0:
        return 0.0
    if val > 1.0:
        return 1.0
    return val


def top_p_flatness(logits_row: np.ndarray, top_p: float) -> float:
    """
    Measure how flat the distribution is within the top-p mass.

    Steps:
      - Compute softmax over raw logits.
      - Sort probabilities descending and accumulate until cumulative >= top_p.
      - Renormalize probabilities within this set and compute normalized entropy:
            flatness = H / ln(N),  where H = -Σ q_i ln q_i and N = len(q).

    Returns a Python float in [0,1]. If the top-p set is degenerate, returns 0.0.
    """
    if not (0.0 < float(top_p) <= 1.0):
        raise ValueError(f"top_p must be in (0,1], got {top_p}")

    row = np.asarray(logits_row, dtype=np.float64)
    if row.ndim != 1:
        row = row.reshape(-1)
    if row.size == 0:
        return 0.0

    lse = logsumexp(row)
    if not math.isfinite(lse):
        return 0.0
    probs = np.exp(row - lse)
    # Sort descending
    order = np.argsort(-probs)
    p_sorted = probs[order]
    csum = np.cumsum(p_sorted)
    # Find smallest prefix with mass >= top_p
    k = int(np.searchsorted(csum, float(top_p), side="left")) + 1
    k = max(1, min(k, p_sorted.size))
    top = p_sorted[:k]
    mass = float(np.sum(top))
    if mass <= 0.0 or k <= 1:
        return 0.0
    q = top / mass
    # Normalized entropy
    # add tiny epsilon to avoid log(0) in degenerate tails
    eps = 1e-12
    H = float(-np.sum(q * np.log(q + eps)))
    denom = math.log(k)
    if denom <= 0.0:
        return 0.0
    flatness = H / denom
    # Clamp for numerical stability
    if flatness < 0.0:
        return 0.0
    if flatness > 1.0:
        return 1.0
    return flatness


def sequence_confidence(token_probs: Iterable[float]) -> Optional[float]:
    """
    Geometric mean over provided token probabilities.
    Returns None if the iterator is empty.
    """
    vals = [float(x) for x in token_probs if x is not None]
    if not vals:
        return None
    logs = [math.log(max(min(v, 1.0), 1e-32)) for v in vals]
    return float(math.exp(sum(logs) / len(logs)))


__all__ = [
    "logsumexp",
    "selected_token_prob",
    "top_p_flatness",
    "sequence_confidence",
]
