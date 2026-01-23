from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Set

import numpy as np

from .logger import IngestAccumulator


def _decode(tok: int, tokenizer) -> Optional[str]:
    if tokenizer is None:
        return None
    try:
        # Direct token decoder
        if hasattr(tokenizer, "decode_token"):
            return str(tokenizer.decode_token(int(tok)))
        # Convert ids to tokens (returns token string, e.g., with BPE markers)
        if hasattr(tokenizer, "convert_ids_to_tokens"):
            try:
                t = tokenizer.convert_ids_to_tokens(int(tok))
                return None if t is None else str(t)
            except Exception:
                pass
        # Generic decode([id]) — may be sync or async
        if hasattr(tokenizer, "decode"):
            res = tokenizer.decode([int(tok)])
            # If awaitable, run in a temporary loop (best effort)
            if hasattr(res, "__await__"):
                # Minimal inline await runner to avoid importing asyncio here
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    return asyncio.run(res)  # type: ignore[arg-type]
                # Running loop present: run in a new loop thread
                out: Optional[str] = None
                err: Optional[BaseException] = None

                def _worker():
                    nonlocal out, err
                    new_loop = asyncio.new_event_loop()
                    try:
                        asyncio.set_event_loop(new_loop)
                        out = new_loop.run_until_complete(res)  # type: ignore[arg-type]
                    except BaseException as e:
                        err = e
                    finally:
                        try:
                            new_loop.close()
                        except Exception:
                            pass

                import threading

                t = threading.Thread(target=_worker, daemon=True)
                t.start()
                t.join()
                if err is not None:
                    return None
                return None if out is None else str(out)
            # Sync path
            return None if res is None else str(res)
    except Exception:
        return None
    return None

def emit_step_events(
    *,
    step: int,
    request_id_order: Sequence[str],
    done_requests: Set[str],
    next_step_tokens: np.ndarray,
    next_step_row_offsets: np.ndarray,
    raw_logits_rows: Dict[int, np.ndarray],
    batch_index_by_request: Dict[str, int],
    req_top_k: Dict[str, int],
    req_top_p: Dict[str, float],
    req_temperature: Dict[str, float],
    adjusted_logits: bool,
    req_accumulators: Dict[str, IngestAccumulator],
    tokenizer: Optional[Any] = None,
    forced_origin: Optional[Dict[str, Optional[str]]] = None,
    step_ts: Optional[int] = None,
) -> None:
    """
    Emit per-request step events (forced/sample). Computes prob/flatness for non-forced using raw logits
    and annotates forced steps with the provided reasons. Safe no-op on any errors. This function must not
    mutate inference state.
    """
    try:
        # Best-effort decoder
        for rid in request_id_order:
            if rid in done_requests:
                continue
            bidx = batch_index_by_request[rid]
            top_k_val = int(req_top_k.get(rid, 0))
            top_p_val = float(req_top_p.get(rid, 1.0))
            temp_val = float(req_temperature.get(rid, 1.0))
            accumulator = req_accumulators.get(rid)
            if accumulator is None:
                continue
            row_offset_for_batch = next_step_row_offsets[bidx]
            if next_step_row_offsets.shape[0] > bidx + 1:
                row_end = next_step_row_offsets[bidx + 1]
            else:
                row_end = None
            toks_for_step = next_step_tokens[row_offset_for_batch:row_end]
            for tok in toks_for_step:
                tok_int = int(tok)
                tok_text = _decode(tok_int, tokenizer)
                row = raw_logits_rows.get(bidx)
                forced_by = None
                if forced_origin is not None:
                    forced_by = forced_origin.get(rid)
                accumulator.emit_step(
                    request_id=rid,
                    step=step,
                    token=tok_int,
                    token_text=tok_text,
                    raw_logits=row,
                    top_k=top_k_val,
                    top_p=top_p_val,
                    temperature=temp_val,
                    adjusted_logits=bool(adjusted_logits),
                    forced=forced_by is not None,
                    forced_by=forced_by,
                    created_at=step_ts,
                )
    except Exception:
        # Best-effort: do not let logging affect generation
        pass


__all__ = ["emit_step_events"]
