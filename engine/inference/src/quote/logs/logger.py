from __future__ import annotations

import json
import threading
import pathlib
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import requests


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class IngestAccumulator:
    """
    Collects inference events and related mod data for a single request.
    The inference loop should only hand raw facts to this class; formatting
    into the ingest payload happens here. Best-effort: exceptions are swallowed.
    """

    _registry: Dict[str, "IngestAccumulator"] = {}
    _lock = threading.Lock()

    def __init__(self, request_id: str) -> None:
        self.request_id = str(request_id)
        self.request: Dict[str, Any] = {"request_id": self.request_id, "created_at": _iso_now()}
        self.events: list[Dict[str, Any]] = []
        self.mod_calls: list[Dict[str, Any]] = []
        self.mod_logs: list[Dict[str, Any]] = []
        self.actions: list[Dict[str, Any]] = []
        self._sequence_order = 0
        self._event_index: Dict[Tuple[str, int], int] = {}
        self._last_event_sequence: Optional[int] = None
        self._finalized = False
        self._prefill_seq: Optional[int] = None
        self._final_tokens: Optional[list[int]] = None
        self._final_text: Optional[str] = None
        self._collection: Optional[int | str] = None  # Collection ID or name to add request to
        self._collection_added_by: Optional[str] = None  # Who added to collection

    # ---- Request metadata ----
    def mark_request_start(
        self,
        *,
        model: Optional[str] = None,
        user_api_key: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        mod_text: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> None:
        try:
            self.request.setdefault("created_at", created_at or _iso_now())
            if model is not None:
                self.request.setdefault("model", model)
            if user_api_key is not None:
                self.request["user_api_key"] = user_api_key
            if max_tokens is not None:
                existing = self.request.get("max_tokens")
                if existing is None or int(existing) < int(max_tokens):
                    self.request["max_tokens"] = int(max_tokens)
            if temperature is not None:
                self.request.setdefault("temperature", float(temperature))
            if mod_text:
                self.request.setdefault("mod_text", mod_text)
        except Exception:
            return

    def mark_request_end(self, *, completed_at: Optional[str] = None) -> None:
        try:
            self.request["completed_at"] = completed_at or _iso_now()
        except Exception:
            return

    def set_inference_stats(self, stats: Dict[str, Any]) -> None:
        try:
            self.request["inference_stats"] = stats
        except Exception:
            return

    def set_final_output(self, token_ids: Optional[list[int]], text: Optional[str]) -> None:
        try:
            if token_ids is not None:
                self._final_tokens = [int(t) for t in token_ids]
                self.request["final_token_ids"] = self._final_tokens
            if text is not None:
                self._final_text = text
                self.request["final_text"] = text
        except Exception:
            return

    # ---- Event helpers ----
    def _add_event_internal(self, event: Dict[str, Any]) -> int:
        event["sequence_order"] = self._sequence_order
        self._last_event_sequence = self._sequence_order
        self.events.append(event)
        self._sequence_order += 1
        return event["sequence_order"]

    def add_event(
        self,
        event_type: str,
        *,
        step: int,
        created_at: Optional[int | float | str] = None,
        **fields: Any,
    ) -> int:
        try:
            if event_type == "Prefilled" and self._prefill_seq is not None:
                return self._prefill_seq
            key = (event_type, int(step))
            event = {"event_type": event_type, "step": int(step)}
            if created_at is not None:
                event["created_at"] = (
                    created_at if isinstance(created_at, str) else datetime.fromtimestamp(float(created_at), tz=timezone.utc).isoformat()
                )
            else:
                event["created_at"] = _iso_now()
            for k, v in fields.items():
                if v is None:
                    continue
                event[k] = v
            seq = self._add_event_internal(event)
            self._event_index[key] = seq
            if event_type == "Prefilled":
                self._prefill_seq = seq
            return seq
        except Exception:
            return -1

    def upsert_event(
        self,
        event_type: str,
        *,
        step: int,
        created_at: Optional[int | float | str] = None,
        **fields: Any,
    ) -> int:
        try:
            key = (event_type, int(step))
            if key not in self._event_index:
                return self.add_event(event_type, step=step, created_at=created_at, **fields)
            seq = self._event_index[key]
            # Update in place
            for ev in self.events:
                if ev.get("sequence_order") == seq:
                    for k, v in fields.items():
                        if v is None:
                            continue
                        ev[k] = v
                    if created_at is not None and "created_at" not in ev:
                        ev["created_at"] = (
                            created_at if isinstance(created_at, str) else datetime.fromtimestamp(float(created_at), tz=timezone.utc).isoformat()
                        )
                    self._last_event_sequence = seq
                    return seq
            # Fallback to add if not found
            return self.add_event(event_type, step=step, created_at=created_at, **fields)
        except Exception:
            return -1

    # ---- Mod call, logs, actions ----
    def add_mod_call(
        self,
        *,
        mod_name: str,
        event_type: str,
        step: int,
        execution_time_ms: Optional[float] = None,
        exception_occurred: Optional[bool] = None,
        exception_message: Optional[str] = None,
        exception_traceback: Optional[str] = None,
    ) -> Optional[int]:
        try:
            key = (event_type, int(step))
            seq = self._event_index.get(key, self._last_event_sequence)
            if seq is None:
                seq = self.add_event(event_type, step=step)
            call = {
                "event_sequence_order": seq,
                "mod_name": mod_name,
                "event_type": event_type,
                "step": int(step),
            }
            if execution_time_ms is not None:
                call["execution_time_ms"] = float(execution_time_ms)
            if exception_occurred is not None:
                call["exception_occurred"] = bool(exception_occurred)
            if exception_message is not None:
                call["exception_message"] = exception_message
            if exception_traceback is not None:
                call["exception_traceback"] = exception_traceback
            call["created_at"] = _iso_now()
            self.mod_calls.append(call)
            return len(self.mod_calls) - 1
        except Exception:
            return None

    def add_mod_log(
        self,
        *,
        mod_call_sequence: int,
        mod_name: str,
        log_message: str,
        log_level: str = "INFO",
        created_at: Optional[int | float | str] = None,
    ) -> None:
        try:
            entry: Dict[str, Any] = {
                "mod_call_sequence": int(mod_call_sequence),
                "mod_name": mod_name,
                "log_message": log_message,
                "log_level": log_level,
            }
            if created_at is not None:
                entry["created_at"] = (
                    created_at if isinstance(created_at, str) else datetime.fromtimestamp(float(created_at), tz=timezone.utc).isoformat()
                )
            else:
                entry["created_at"] = _iso_now()
            self.mod_logs.append(entry)
        except Exception:
            return

    def add_action(
        self,
        *,
        mod_call_sequence: Optional[int],
        action_type: str,
        action_order: int = 0,
        created_at: Optional[int | float | str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            if mod_call_sequence is None:
                return
            entry: Dict[str, Any] = {
                "mod_call_sequence": int(mod_call_sequence),
                "action_type": action_type,
                "action_order": int(action_order),
            }
            if created_at is not None:
                entry["created_at"] = (
                    created_at if isinstance(created_at, str) else datetime.fromtimestamp(float(created_at), tz=timezone.utc).isoformat()
                )
            else:
                entry["created_at"] = _iso_now()
            if details:
                entry["details"] = details
            self.actions.append(entry)
        except Exception:
            return

    # ---- Step emission ----
    def emit_step(
        self,
        *,
        request_id: str,
        step: int,
        token: int,
        token_text: Optional[str],
        raw_logits: Any,
        top_k: int,
        top_p: float,
        temperature: float,
        adjusted_logits: bool,
        forced: bool,
        forced_by: Optional[str],
        created_at: Optional[int] = None,
    ) -> None:
        try:
            event_type = "Added" if forced else "Sampled"
            fields: Dict[str, Any] = {
                "sequence_order": None,  # populated by upsert_event
                "created_at": created_at,
                "top_tokens": None,
                "adjusted_logits": bool(adjusted_logits),
                "forced": bool(forced),
                "forced_by": forced_by,
                "top_k": int(top_k),
                "top_p": float(top_p),
                "temperature": float(temperature),
            }
            if forced:
                fields["added_tokens"] = [int(token)]
                fields["added_token_count"] = 1
            else:
                fields["sampled_token"] = int(token)
                if token_text is not None:
                    fields["token_text"] = token_text
            self.upsert_event(
                event_type,
                step=step,
                created_at=created_at,
                **fields,
            )
        except Exception:
            return

    # ---- Collection ----
    def set_collection(self, collection: Optional[int | str], added_by: Optional[str] = None) -> None:
        """Set the collection to add this request to after ingestion."""
        self._collection = collection
        self._collection_added_by = added_by

    def _add_to_collection(self) -> None:
        """Add the request to a collection after successful ingestion."""
        if self._collection is None:
            return
        try:
            base_url = os.environ.get("QUOTE_LOG_INGEST_URL", "http://localhost:6767/v1/ingest")
            # Extract base URL (remove /v1/ingest suffix)
            if base_url.endswith("/v1/ingest"):
                base_url = base_url[:-10]
            elif base_url.endswith("/v1/ingest/"):
                base_url = base_url[:-11]
            
            # Get user API key for authentication
            user_api_key = self.request.get("user_api_key")
            headers = {}
            if user_api_key:
                headers["X-API-Key"] = user_api_key
            
            collection_id = self._collection

            # If collection is a string (name), we need to find or create the collection
            if isinstance(collection_id, str):
                # Try to find existing collection by name
                list_url = f"{base_url}/collections"
                try:
                    resp = requests.get(list_url, headers=headers, timeout=10)
                    if resp.ok:
                        data = resp.json()
                        collections = data.get("collections", [])
                        collection_name = collection_id  # Save the name for creation
                        found = False
                        for c in collections:
                            if c.get("name") == collection_name:
                                collection_id = c.get("id")
                                found = True
                                print(f"[COLLECTION][{self.request_id}] Found existing collection '{collection_name}' with ID {collection_id}")
                                break
                        
                        if not found:
                            # Collection not found, create it
                            print(f"[COLLECTION][{self.request_id}] Collection '{collection_name}' not found, creating...")
                            create_resp = requests.post(
                                list_url,
                                json={"name": collection_name, "created_by": self._collection_added_by},
                                headers=headers,
                                timeout=10
                            )
                            if create_resp.ok:
                                create_data = create_resp.json()
                                collection_id = create_data.get("collection", {}).get("id")
                                print(f"[COLLECTION][{self.request_id}] Created collection '{collection_name}' with ID {collection_id}")
                            else:
                                print(f"[COLLECTION_ERROR][{self.request_id}] Failed to create collection: {create_resp.text}")
                                return
                    elif resp.status_code == 401:
                        print(f"[COLLECTION_ERROR][{self.request_id}] Authentication required - no valid API key provided")
                        return
                    else:
                        print(f"[COLLECTION_ERROR][{self.request_id}] Failed to list collections: {resp.status_code} {resp.text}")
                        return
                except Exception as e:
                    print(f"[COLLECTION_ERROR][{self.request_id}] Failed to find/create collection: {e}")
                    return
            
            # Validate that we have a numeric collection ID
            if collection_id is None:
                print(f"[COLLECTION_ERROR][{self.request_id}] Collection ID is None after lookup/create")
                return
            
            if isinstance(collection_id, str):
                # Still a string - lookup/create failed to resolve to numeric ID
                print(f"[COLLECTION_ERROR][{self.request_id}] Failed to resolve collection name '{collection_id}' to numeric ID")
                return
            
            if not isinstance(collection_id, int):
                print(f"[COLLECTION_ERROR][{self.request_id}] Invalid collection ID type: {type(collection_id)}")
                return
                
            # Add request to collection
            add_url = f"{base_url}/collections/{collection_id}/requests"
            payload = {
                "request_id": self.request_id,
                "added_by": self._collection_added_by,
            }
            print(f"[COLLECTION][POST] {add_url} - Adding request {self.request_id} to collection {collection_id}")
            resp = requests.post(add_url, json=payload, headers=headers, timeout=10)
            if resp.ok:
                print(f"[COLLECTION][{self.request_id}] Added to collection {collection_id}")
            elif resp.status_code == 401:
                print(f"[COLLECTION_ERROR][{self.request_id}] Authentication required - no valid API key provided")
            else:
                print(f"[COLLECTION_ERROR][{self.request_id}] Failed to add to collection: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"[COLLECTION_ERROR][{self.request_id}] Exception adding to collection: {e}")

    # ---- Finalize ----
    def finalize(self) -> None:
        if self._finalized:
            return
        ingest_success = False
        try:
            payload = {
                "request": self.request,
                "events": self.events,
                "mod_calls": self.mod_calls,
                "mod_logs": self.mod_logs,
                "actions": self.actions,
            }
            print(f"[INGEST_PAYLOAD][{self.request_id}] {json.dumps(payload, ensure_ascii=False)}")
            try:
                url = os.environ.get("QUOTE_LOG_INGEST_URL", "http://localhost:6767/v1/ingest")
                print("[INGEST][POST]", url)
                timeout = float(os.environ.get("QUOTE_LOG_INGEST_TIMEOUT", "25"))
                resp = requests.post(url, json=payload, timeout=timeout)
                if not resp.ok:
                    print(f"[INGEST_ERROR][{self.request_id}] status={resp.status_code} body={resp.text}")
                else:
                    ingest_success = True
            except Exception as e:
                print(f"[INGEST_ERROR][{self.request_id}] failed to POST: {e}")
        except Exception:
            return
        finally:
            self._finalized = True
            # Add to collection after successful ingest
            if ingest_success and self._collection is not None:
                self._add_to_collection()
            with self._lock:
                try:
                    if self.request_id in self._registry:
                        del self._registry[self.request_id]
                except Exception:
                    pass

    def snapshot_to_file(self, path: str) -> None:
        """Persist current payload to disk so another process can merge/print."""
        try:
            p = pathlib.Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "request": self.request,
                "events": self.events,
                "mod_calls": self.mod_calls,
                "mod_logs": self.mod_logs,
                "actions": self.actions,
            }
            p.write_text(json.dumps(payload, ensure_ascii=False))
        except Exception:
            return


def get_accumulator(request_id: str) -> IngestAccumulator:
    with IngestAccumulator._lock:
        if request_id in IngestAccumulator._registry:
            return IngestAccumulator._registry[request_id]
        acc = IngestAccumulator(request_id)
        IngestAccumulator._registry[request_id] = acc
        return acc


__all__ = ["IngestAccumulator", "get_accumulator"]
