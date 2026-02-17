# Concordance System Architecture

This is the high-level map of the system. Detailed architecture docs live in each subproject:

- Engine: [`engine/ARCHITECTURE.md`](engine/ARCHITECTURE.md)
- Backend: [`backend/ARCHITECTURE.md`](backend/ARCHITECTURE.md)
- Frontend: [`frontend/ARCHITECTURE.md`](frontend/ARCHITECTURE.md)

## 1. System Topology

```text
Frontend (React/TS)
  -> Backend (Rust/Axum + Postgres)
  <- WebSocket stream (new logs)

Playground page (/playground)
  -> Backend /playground/inference
  -> MAX OpenAI-compatible engine stack (/v1/chat/completions)
  -> Backend /v1/ingest (trace persistence)

Activation Explorer page (/activations)
  -> Backend /playground/activations/*
  -> HF inference service (/hf/generate) with inline SAE

Playground SAE sidecar
  -> Backend /playground/extract-features + /playground/analyze-features
  -> SAE service (/extract_features, /analyze_features)
```

## 2. Core End-to-End Flows

### 2.1 Inference Observability Flow

1. Client sends chat request to engine (`/v1/chat/completions`)
2. Engine executes token loop + mods
3. Engine finalizes ingest payload and POSTs backend `/v1/ingest`
4. Backend stores normalized trace in Postgres
5. Backend pushes `new_log` events over `/logs/stream`
6. Frontend updates Logs list and detail views

### 2.2 Playground Flow

1. Frontend gets temporary playground API key (`/playground/api-key`)
2. Frontend optionally generates + uploads mod
3. Frontend triggers `/playground/inference` -> backend forwards to MAX OpenAI-compatible `/v1/chat/completions`
4. Frontend polls `/logs` + `/logs/:request_id` for full trace data
5. Optional SAE panel uses separate post-hoc sidecar endpoints (`/playground/extract-features`, `/playground/analyze-features`)

### 2.3 Activation Explorer Flow

1. Frontend `/activations` calls `/playground/activations/run`
2. Backend calls HF inference service (`/hf/generate`)
3. Backend derives/stores run summary + preview timeline
4. Frontend queries summary/rows/top-features endpoints for inspection

### 2.4 Engine Split Summary

- Base Playground: MAX OpenAI-compatible runtime + post-hoc SAE sidecar
- Activation Explorer: HF runtime + inline SAE in generation call
- Shared expectation: downstream trace/mod/action semantics stay mostly engine-agnostic at backend ingest/storage boundaries

## 3. Data Ownership

- Engine owns runtime execution state and mod dispatch lifecycle
- Backend owns durable trace data, auth scopes, and shareability state
- Frontend owns presentation state and query orchestration

## 4. Primary Storage

- Backend: Postgres tables for requests/events/mod_calls/mod_logs/actions + activation explorer index/preview
- Engine (optional/local): DuckDB + Parquet activation feature store
- Frontend: browser localStorage for API key and UI preferences

## 5. Integration Notes

- activation health includes both `sae_reachable` and `sae_service_reachable` for compatibility

See implementation details and code anchors in the subproject docs linked above.
