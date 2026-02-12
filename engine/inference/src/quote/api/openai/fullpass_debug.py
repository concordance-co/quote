from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from quote.storage.activations import ActivationQueries, ActivationStore
from quote.storage.activations.schema import TABLE_ACTIVATION_FEATURES
from quote.backends.huggingface import HuggingFaceBackend
from quote.backends.interface import ActivationConfig, BackendConfig, GenerationConfig, SAEConfig
from quote.runtime.config import default_activation_config, default_sae_config
from quote.interp.sae_extract import MinimalSAEExtractor
from quote.runtime.generation import GenerationResult, generate
from quote.mods.manager import ModManager

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _encode_prompt(tokenizer: Any, prompt: str) -> list[int]:
    messages = [
        {"role": "system", "content": "You are concise."},
        {"role": "user", "content": prompt},
    ]
    if hasattr(tokenizer, "apply_chat_template"):
        try:
            maybe_ids = tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
            )
            if hasattr(maybe_ids, "tolist"):
                maybe_ids = maybe_ids.tolist()
            if isinstance(maybe_ids, list) and maybe_ids:
                return [int(t) for t in maybe_ids]
        except Exception:
            pass
    return [int(t) for t in tokenizer.encode(prompt, add_special_tokens=True)]


def _summarize_event(event: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "event_type": type(event).__name__,
        "step": int(getattr(event, "step", 0)),
    }
    if hasattr(event, "sampled_token"):
        item["sampled_token"] = int(getattr(event, "sampled_token"))
    if hasattr(event, "added_tokens"):
        item["added_tokens"] = [int(t) for t in getattr(event, "added_tokens", [])]
        item["forced"] = bool(getattr(event, "forced", False))
    if hasattr(event, "max_steps"):
        item["max_steps"] = int(getattr(event, "max_steps", 0))
    return item


def _summarize_action(action: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"action_type": type(action).__name__}
    if hasattr(action, "tokens") and getattr(action, "tokens") is not None:
        item["tokens"] = [int(t) for t in getattr(action, "tokens")]
    if hasattr(action, "n"):
        item["backtrack_n"] = int(getattr(action, "n", 0))
    if hasattr(action, "tool_calls"):
        item["tool_calls"] = getattr(action, "tool_calls")
    return item


class _FullpassRuntime:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._backend: HuggingFaceBackend | None = None
        self._backend_cfg: BackendConfig | None = None
        self._tokenizer: Any = None
        self._activation_cfg: ActivationConfig = default_activation_config()
        self._activation_store: ActivationStore | None = None
        if self._activation_cfg.enabled:
            self._activation_store = ActivationStore(self._activation_cfg)
            self._activation_store.setup()
        logger.info(
            "fullpass_debug runtime initialized activations_enabled=%s db_path=%s parquet_path=%s",
            self._activation_cfg.enabled,
            self._activation_cfg.db_path,
            self._activation_cfg.parquet_path,
        )

    def _ensure_backend(self, cfg: BackendConfig) -> None:
        with self._lock:
            if (
                self._backend is not None
                and self._backend_cfg is not None
                and self._backend_cfg.model_id == cfg.model_id
                and self._backend_cfg.device == cfg.device
                and self._backend_cfg.hidden_state_layer == cfg.hidden_state_layer
                and self._backend_cfg.dtype == cfg.dtype
                and self._backend_cfg.extract_attention == cfg.extract_attention
            ):
                logger.info(
                    "fullpass_debug backend reuse model=%s device=%s layer=%s dtype=%s",
                    cfg.model_id,
                    cfg.device,
                    cfg.hidden_state_layer,
                    cfg.dtype,
                )
                return
            if self._backend is not None:
                try:
                    logger.info("fullpass_debug backend shutdown prior_model=%s", self._backend_cfg.model_id if self._backend_cfg else "unknown")
                    self._backend.shutdown()
                except Exception:
                    pass
            logger.info(
                "fullpass_debug backend load model=%s device=%s layer=%s dtype=%s attention=%s",
                cfg.model_id,
                cfg.device,
                cfg.hidden_state_layer,
                cfg.dtype,
                cfg.extract_attention,
            )
            backend = HuggingFaceBackend(cfg)
            backend.load_model(cfg.model_id, cfg)
            self._backend = backend
            self._backend_cfg = cfg
            self._tokenizer = backend.tokenizer()

    def run(self, body: dict[str, Any]) -> dict[str, Any]:
        prompt = str(body.get("prompt", "")).strip()
        if not prompt:
            raise HTTPException(status_code=400, detail="prompt is required")
        model_id = str(
            body.get("model_id")
            or os.environ.get("QUOTE_FULLPASS_MODEL")
            or os.environ.get("CONCORDANCE_MODEL")
            or "meta-llama/Llama-3.1-8B-Instruct"
        )
        max_tokens = int(body.get("max_tokens", 64))
        temperature = float(body.get("temperature", 0.0))
        top_p = float(body.get("top_p", 1.0))
        top_k = int(body.get("top_k", 1))
        extract_attention = bool(body.get("extract_attention", False))
        collect_activations = bool(body.get("collect_activations", True))
        inline_sae = bool(body.get("inline_sae", True))
        run_start = time.perf_counter()

        backend_cfg = BackendConfig(
            backend_type="huggingface",
            model_id=model_id,
            device=str(body.get("device") or os.environ.get("QUOTE_FULLPASS_DEVICE", "auto")),
            hidden_state_layer=int(body.get("hidden_layer", os.environ.get("QUOTE_FULLPASS_LAYER", "16"))),
            dtype=str(body.get("dtype") or os.environ.get("QUOTE_FULLPASS_DTYPE", "auto")),
            extract_attention=extract_attention,
        )
        self._ensure_backend(backend_cfg)
        assert self._backend is not None
        assert self._tokenizer is not None

        request_id = str(body.get("request_id") or f"ui-{uuid.uuid4().hex[:12]}")
        input_ids = _encode_prompt(self._tokenizer, prompt)
        gen_cfg = GenerationConfig(
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
        )

        activation_store = self._activation_store if (collect_activations and self._activation_store is not None) else None
        sae_extractor = None
        if collect_activations and inline_sae:
            base_cfg = default_sae_config()
            sae_cfg = SAEConfig(
                enabled=True,
                mode="inline",
                sae_id=str(body.get("sae_id") or os.environ.get("QUOTE_FULLPASS_SAE_ID") or base_cfg.sae_id),
                layer=int(body.get("sae_layer", os.environ.get("QUOTE_FULLPASS_SAE_LAYER", base_cfg.layer))),
                top_k=int(body.get("sae_top_k", os.environ.get("QUOTE_FULLPASS_SAE_TOP_K", base_cfg.top_k))),
                sae_local_path=(
                    body.get("sae_local_path")
                    or os.environ.get("QUOTE_FULLPASS_SAE_LOCAL_PATH")
                    or os.environ.get("CONCORDANCE_SAE_LOCAL_PATH")
                    or base_cfg.sae_local_path
                ),
            )
            sae_extractor = MinimalSAEExtractor(sae_cfg)
            logger.info(
                "fullpass_debug run request_id=%s model=%s prompt_chars=%s max_tokens=%s inline_sae=1 sae_id=%s sae_layer=%s sae_top_k=%s local_sae_path=%s",
                request_id,
                model_id,
                len(prompt),
                max_tokens,
                sae_cfg.sae_id,
                sae_cfg.layer,
                sae_cfg.top_k,
                sae_cfg.sae_local_path,
            )
        else:
            logger.info(
                "fullpass_debug run request_id=%s model=%s prompt_chars=%s max_tokens=%s inline_sae=%s collect_activations=%s",
                request_id,
                model_id,
                len(prompt),
                max_tokens,
                int(inline_sae),
                int(collect_activations),
            )

        mod_manager = ModManager([], tokenizer=self._tokenizer)
        result: GenerationResult = generate(
            backend=self._backend,
            input_ids=input_ids,
            request_id=request_id,
            mod_manager=mod_manager,
            config=gen_cfg,
            activation_store=activation_store,
            sae_extractor=sae_extractor,
        )

        activations_preview: list[dict[str, Any]] = []
        if activation_store is not None:
            try:
                conn = activation_store._get_conn()  # noqa: SLF001 - debug endpoint
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
                        sae_layer
                    FROM {TABLE_ACTIVATION_FEATURES}
                    WHERE request_id = ?
                    ORDER BY step ASC, token_position ASC, rank ASC
                    LIMIT 200
                    """,
                    [request_id],
                ).fetchall()
                activations_preview = [
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
                    }
                    for r in rows
                ]
            except Exception:
                activations_preview = []

        unique_features: list[int] = []
        seen: set[int] = set()
        for row in activations_preview:
            fid = int(row["feature_id"])
            if fid in seen:
                continue
            seen.add(fid)
            unique_features.append(fid)
            if len(unique_features) >= 20:
                break

        logger.info(
            "fullpass_debug complete request_id=%s duration_ms=%s output_tokens=%s events=%s actions=%s activation_rows=%s unique_features=%s terminal_action=%s",
            request_id,
            int((time.perf_counter() - run_start) * 1000),
            len(result.output_ids),
            len(result.events),
            len(result.actions),
            len(activations_preview),
            len(unique_features),
            result.metadata.get("terminal_action"),
        )

        return {
            "request_id": request_id,
            "model_id": model_id,
            "output_text": result.output_text,
            "output_ids": [int(t) for t in result.output_ids],
            "metadata": result.metadata,
            "events": [_summarize_event(e) for e in result.events],
            "actions": [_summarize_action(a) for a in result.actions],
            "activations_preview": activations_preview,
            "feature_ids": unique_features,
        }

    def feature_deltas(self, request_id: str, feature_id: int, sae_layer: int | None = None) -> list[dict[str, Any]]:
        if self._activation_store is None:
            return []
        queries = ActivationQueries(self._activation_cfg)
        try:
            return queries.feature_deltas_over_time(
                request_id=request_id,
                feature_id=feature_id,
                sae_layer=sae_layer,
                limit=512,
            )
        finally:
            queries.close()


def register_fullpass_debug_routes(app: FastAPI) -> None:
    runtime = _FullpassRuntime()

    @app.get("/debug/fullpass", response_class=HTMLResponse)
    async def debug_fullpass_ui():
        return HTMLResponse(_UI_HTML)

    @app.post("/debug/fullpass/run")
    async def debug_fullpass_run(body: dict = Body(...)):
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")
        try:
            return runtime.run(body)
        except HTTPException:
            raise
        except Exception:
            logger.exception("fullpass_debug run failed")
            raise HTTPException(status_code=500, detail="fullpass debug run failed")

    @app.get("/debug/fullpass/feature-deltas")
    async def debug_fullpass_feature_deltas(
        request_id: str = Query(...),
        feature_id: int = Query(...),
        sae_layer: int | None = Query(default=None),
    ):
        rows = runtime.feature_deltas(request_id=request_id, feature_id=int(feature_id), sae_layer=sae_layer)
        logger.info(
            "fullpass_debug feature_deltas request_id=%s feature_id=%s sae_layer=%s rows=%s",
            request_id,
            int(feature_id),
            sae_layer,
            len(rows),
        )
        return {
            "request_id": request_id,
            "feature_id": int(feature_id),
            "rows": rows,
        }


_UI_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Fullpass Debug UI</title>
  <style>
    :root {
      --bg: #f4f1e8;
      --panel: #fffaf0;
      --ink: #1e1e1e;
      --muted: #5c5c5c;
      --accent: #0d9488;
      --line: #ddd1ba;
      --ok: #0f766e;
      --err: #b91c1c;
    }
    body {
      margin: 0;
      font-family: "Iosevka Aile", "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background: radial-gradient(circle at 10% 10%, #fffbe8 0%, var(--bg) 55%);
    }
    .wrap {
      max-width: 1200px;
      margin: 24px auto;
      padding: 0 16px 48px;
    }
    .title {
      margin: 0 0 8px;
      font-size: 30px;
      letter-spacing: 0.2px;
    }
    .subtitle {
      margin: 0 0 18px;
      color: var(--muted);
    }
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
    }
    .panel {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 12px;
      padding: 14px;
      box-shadow: 0 1px 0 rgba(0,0,0,0.05);
    }
    label {
      font-size: 12px;
      color: var(--muted);
      display: block;
      margin-bottom: 4px;
    }
    input, textarea, select, button {
      font: inherit;
    }
    input, textarea, select {
      width: 100%;
      box-sizing: border-box;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: #fff;
      padding: 8px 10px;
      margin-bottom: 10px;
    }
    textarea {
      min-height: 86px;
      resize: vertical;
    }
    .row {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }
    .checks {
      display: flex;
      gap: 14px;
      margin: 6px 0 12px;
    }
    .checks label {
      display: flex;
      align-items: center;
      gap: 6px;
      margin: 0;
      color: var(--ink);
      font-size: 13px;
    }
    button {
      border: 0;
      border-radius: 10px;
      padding: 10px 14px;
      background: linear-gradient(180deg, #14b8a6, var(--accent));
      color: white;
      font-weight: 600;
      cursor: pointer;
    }
    button:disabled {
      opacity: 0.5;
      cursor: default;
    }
    .status {
      margin: 10px 0 0;
      font-size: 13px;
      color: var(--muted);
    }
    .ok { color: var(--ok); }
    .err { color: var(--err); }
    .mono {
      font-family: "Iosevka Term", "SFMono-Regular", Menlo, monospace;
      font-size: 12px;
      white-space: pre-wrap;
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      max-height: 280px;
      overflow: auto;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }
    th, td {
      text-align: left;
      border-bottom: 1px solid var(--line);
      padding: 6px 4px;
    }
    @media (max-width: 900px) {
      .grid { grid-template-columns: 1fr; }
      .row { grid-template-columns: 1fr 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <h1 class="title">Fullpass Debug UI</h1>
    <p class="subtitle">Run local HF fullpass generation with optional inline SAE and inspect feature activations.</p>
    <div class="grid">
      <section class="panel">
        <label for="prompt">Prompt</label>
        <textarea id="prompt">Give me a short paragraph about mechanistic interpretability and feature tracking.</textarea>
        <div class="row">
          <div>
            <label for="model">Model</label>
            <input id="model" value="meta-llama/Llama-3.1-8B-Instruct" />
          </div>
          <div>
            <label for="max_tokens">Max Tokens</label>
            <input id="max_tokens" type="number" value="64" />
          </div>
          <div>
            <label for="temperature">Temperature</label>
            <input id="temperature" type="number" value="0" step="0.1" />
          </div>
          <div>
            <label for="top_k">Top K</label>
            <input id="top_k" type="number" value="1" />
          </div>
        </div>
        <div class="row">
          <div>
            <label for="sae_id">SAE Release</label>
            <input id="sae_id" value="llama_scope_lxr_8x" />
          </div>
          <div>
            <label for="sae_layer">SAE Layer</label>
            <input id="sae_layer" type="number" value="16" />
          </div>
          <div>
            <label for="sae_top_k">SAE Top K</label>
            <input id="sae_top_k" type="number" value="20" />
          </div>
          <div>
            <label for="feature_id">Feature ID (for deltas)</label>
            <input id="feature_id" type="number" placeholder="auto" />
          </div>
        </div>
        <div class="checks">
          <label><input id="collect_activations" type="checkbox" checked /> Collect activations</label>
          <label><input id="inline_sae" type="checkbox" checked /> Inline SAE</label>
        </div>
        <button id="run_btn">Run Fullpass</button>
        <div id="status" class="status">Idle.</div>
      </section>
      <section class="panel">
        <h3>Output</h3>
        <div id="output_text" class="mono"></div>
        <h3>Metadata</h3>
        <div id="metadata" class="mono"></div>
      </section>
      <section class="panel">
        <h3>Events / Actions</h3>
        <div id="events_actions" class="mono"></div>
      </section>
      <section class="panel">
        <h3>Feature Deltas</h3>
        <div id="feature_deltas" class="mono"></div>
      </section>
      <section class="panel" style="grid-column: 1 / -1;">
        <h3>Activation Preview (Top Rows)</h3>
        <table>
          <thead>
            <tr>
              <th>step</th>
              <th>tok_pos</th>
              <th>tok_id</th>
              <th>feature_id</th>
              <th>activation</th>
              <th>rank</th>
              <th>mode</th>
            </tr>
          </thead>
          <tbody id="activation_rows"></tbody>
        </table>
      </section>
    </div>
  </div>
  <script>
    const el = (id) => document.getElementById(id);
    const statusEl = el("status");
    let lastRequestId = null;
    let lastSaeLayer = null;

    function setStatus(msg, cls = "") {
      statusEl.className = "status " + cls;
      statusEl.textContent = msg;
    }

    function j(obj) {
      return JSON.stringify(obj, null, 2);
    }

    async function fetchDeltas(requestId, featureId, saeLayer) {
      const url = `/debug/fullpass/feature-deltas?request_id=${encodeURIComponent(requestId)}&feature_id=${encodeURIComponent(featureId)}&sae_layer=${encodeURIComponent(saeLayer)}`;
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(await resp.text());
      return await resp.json();
    }

    async function run() {
      el("run_btn").disabled = true;
      setStatus("Running fullpass...", "");
      try {
        const payload = {
          prompt: el("prompt").value,
          model_id: el("model").value,
          max_tokens: parseInt(el("max_tokens").value || "64", 10),
          temperature: parseFloat(el("temperature").value || "0"),
          top_k: parseInt(el("top_k").value || "1", 10),
          collect_activations: el("collect_activations").checked,
          inline_sae: el("inline_sae").checked,
          sae_id: el("sae_id").value,
          sae_layer: parseInt(el("sae_layer").value || "16", 10),
          sae_top_k: parseInt(el("sae_top_k").value || "20", 10),
        };
        const resp = await fetch("/debug/fullpass/run", {
          method: "POST",
          headers: {"content-type": "application/json"},
          body: JSON.stringify(payload),
        });
        if (!resp.ok) {
          throw new Error(await resp.text());
        }
        const data = await resp.json();
        lastRequestId = data.request_id;
        lastSaeLayer = payload.sae_layer;
        el("output_text").textContent = data.output_text || "";
        el("metadata").textContent = j({
          request_id: data.request_id,
          model_id: data.model_id,
          output_ids: data.output_ids,
          metadata: data.metadata,
          feature_ids: data.feature_ids,
        });
        el("events_actions").textContent = j({
          events: data.events,
          actions: data.actions,
        });

        const rows = data.activations_preview || [];
        const tbody = el("activation_rows");
        tbody.innerHTML = "";
        for (const r of rows) {
          const tr = document.createElement("tr");
          tr.innerHTML = `<td>${r.step}</td><td>${r.token_position}</td><td>${r.token_id ?? ""}</td><td>${r.feature_id}</td><td>${r.activation_value.toFixed(4)}</td><td>${r.rank}</td><td>${r.source_mode}</td>`;
          tbody.appendChild(tr);
        }

        let featureId = parseInt(el("feature_id").value || "", 10);
        if (!Number.isFinite(featureId)) {
          featureId = (data.feature_ids && data.feature_ids.length > 0) ? data.feature_ids[0] : NaN;
          if (Number.isFinite(featureId)) {
            el("feature_id").value = String(featureId);
          }
        }
        if (Number.isFinite(featureId) && lastRequestId) {
          const deltas = await fetchDeltas(lastRequestId, featureId, lastSaeLayer);
          el("feature_deltas").textContent = j(deltas.rows || []);
        } else {
          el("feature_deltas").textContent = "No feature rows found for this request.";
        }
        setStatus("Run complete.", "ok");
      } catch (err) {
        el("feature_deltas").textContent = "";
        setStatus(`Error: ${err.message || err}`, "err");
      } finally {
        el("run_btn").disabled = false;
      }
    }

    el("run_btn").addEventListener("click", run);
  </script>
</body>
</html>
"""
