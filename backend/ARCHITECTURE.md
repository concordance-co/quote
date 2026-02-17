# Thunder Backend Architecture

This document describes how the backend is structured today, how requests flow through it, and where key schemas/contracts live.

## 1. Role in the System

The backend is the system-of-record and API surface for:

- ingesting full inference traces from the engine (`POST /v1/ingest`)
- serving logs and log detail (`GET /logs`, `GET /logs/:request_id`)
- streaming new logs to the UI (`GET /logs/stream` via WebSocket)
- auth/key management and scoped data access
- playground proxy endpoints (mod generation/upload/inference + feature endpoints)
- activation explorer run indexing and query APIs
- sharing/private-public toggles for requests and collections

## 2. Boot Sequence

Primary startup path:

- `backend/src/server.rs:12` connects Postgres
- `backend/src/server.rs:24` initializes `AppState` with cache size
- `backend/src/server.rs:33` warms cache with latest logs
- `backend/src/server.rs:35` builds the router

Key boot block:

```rust
pub async fn run(config: Config) -> anyhow::Result<()> {
    let pool = PgPool::connect(&config.database_url).await?;
    let state = AppState::with_cache_size(pool, config.cache_max_bytes);
    warm_cache(&state.db_pool, &state.log_cache, 50).await;
    let app = routes::build_router(state);
    // bind + serve
}
```

## 3. Runtime State and Caching

`AppState` (`backend/src/utils/state.rs:57`) carries:

- `db_pool`
- `log_cache` (`LogCache`, memory-aware LRU)
- `log_events_tx` broadcast channel for live log events
- `auth` (pool + API-key cache)
- short-lived TTL caches for collections/discussions/public tokens

### 3.1 Log Cache

`LogCache` (`backend/src/utils/cache.rs:177`) is a size-bounded in-memory LRU cache for hydrated `LogResponse` payloads.

- default max size: `2_800_000_000` bytes (`backend/src/utils/cache.rs:20`)
- evicts least-recently-used entries when insertion exceeds limit (`backend/src/utils/cache.rs:261`)
- startup pre-warm via `warm_cache` (`backend/src/handlers/logs.rs:1553`)

### 3.2 Body Limit

Request bodies are capped at **75MB**:

- constant: `backend/src/utils/body_limit.rs:15`
- middleware + `DefaultBodyLimit` applied in router: `backend/src/routes.rs:479-480`

## 4. Router and API Surface

Router assembly is centralized in `backend/src/routes.rs:109`.

Important route groups:

- auth: `/auth/*`
- logs + stream: `/logs`, `/logs/stream`, `/logs/:request_id`
- collections/discussions/favorites/tags
- public sharing: `/share/*`
- ingest: `/v1/ingest` (`backend/src/routes.rs:348`)
- playground: `/playground/*`
- activation explorer: `/playground/activations/*`

Frontend page mapping note:
- user-facing Activation Explorer page route is `/activations` in the SPA, which calls this backend API namespace.

Ingest and body-limit wiring:

```rust
.route("/v1/ingest", post(ingest_payload).options(|| async { StatusCode::NO_CONTENT }))
.layer(middleware::from_fn(body_limit_middleware))
.layer(DefaultBodyLimit::max(MAX_BODY_SIZE))
```

Source: `backend/src/routes.rs:347-350`, `backend/src/routes.rs:479-480`.

## 5. Authentication and Access Control

Header: `X-API-Key` (`backend/src/utils/auth.rs:21`).

Validation chain (`backend/src/utils/auth.rs:155`):

1. hashed lookup in `api_keys` (`backend/src/utils/auth.rs:172`)
2. `allowed_api_key` direct match (`backend/src/utils/auth.rs:232`)
3. fallback: key exists as `requests.user_api_key` (`backend/src/utils/auth.rs:283`)

Implications:

- admin keys can see all
- non-admin keys are scoped to one `allowed_api_key`
- public-share endpoints intentionally redact `user_api_key`

## 6. Ingest Write Path (Engine -> Backend)

Entry: `backend/src/handlers/ingest/mod.rs:27`.

The handler runs a single transaction with ordered replacement semantics:

1. `persist_request` (`backend/src/handlers/ingest/persist.rs:120`)
2. `replace_events` (`backend/src/handlers/ingest/persist.rs:184`)
3. `replace_mod_calls` (`backend/src/handlers/ingest/persist.rs:277`)
4. `replace_mod_logs` (`backend/src/handlers/ingest/persist.rs:377`)
5. `replace_actions` (`backend/src/handlers/ingest/persist.rs:470`)

Then it:

- write-through caches the hydrated response (`backend/src/handlers/ingest/mod.rs:64-66`)
- broadcasts `NewLogEvent` for live clients (`backend/src/handlers/ingest/mod.rs:85-98`)

Core flow block:

```rust
let mut tx = state.db_pool.begin().await?;
persist_request(&mut tx, request).await?;
let event_ids = replace_events(&mut tx, request, &payload.events).await?;
let mod_call_ids = replace_mod_calls(&mut tx, request, &payload.mod_calls, &event_ids).await?;
replace_mod_logs(&mut tx, request, &payload.mod_logs, &mod_call_ids).await?;
replace_actions(&mut tx, request, &payload.actions, &mod_call_ids).await?;
tx.commit().await?;
```

Batch sizes are tuned for Postgres parameter limits (`backend/src/handlers/ingest/persist.rs:9-12`).

### 6.1 Ingest Payload Contract

`FullIngestPayload` schema is defined in `backend/src/handlers/ingest/payload.rs:12`:

- `request`
- `events[]`
- `mod_calls[]`
- `mod_logs[]`
- `actions[]`

Enums are PascalCase-compatible with engine output:

- `EventType`: `Prefilled | ForwardPass | Added | Sampled` (`backend/src/handlers/ingest/payload.rs:194`)
- `ActionType`: includes `AdjustedPrefill`, `ForceTokens`, `Backtrack`, etc. (`backend/src/handlers/ingest/payload.rs:216`)

The ingest payload is intentionally runtime-agnostic:

- it stores trace semantics (`request/events/mod_calls/mod_logs/actions`) rather than an engine discriminator
- there is no explicit `engine_type` field in `RequestRecord` (`backend/src/handlers/ingest/payload.rs:29-59`)

## 7. Read Path (Logs API)

### 7.1 List + Stream

- list summaries: `backend/src/handlers/logs.rs:486`
- websocket stream: `backend/src/handlers/logs.rs:344`

Stream behavior:

- requires `api_key` query param
- admin receives all events
- non-admin events are filtered to allowed key
- lag events are emitted as `{ type: "lagged", missed: n }`

### 7.2 Log Detail

`get_log` (`backend/src/handlers/logs.rs:1082`) performs:

1. optional auth extraction
2. cache lookup (`backend/src/handlers/logs.rs:1131`)
3. access checks (public/admin/owner)
4. DB hydration on miss via `fetch_log_response` (`backend/src/handlers/logs.rs:665`)
5. cache insert + PII redaction for non-admin

## 8. Public Sharing Flows

Request sharing handlers:

- make request public: `backend/src/handlers/logs.rs:1623`
- make request private: `backend/src/handlers/logs.rs:1696`
- get public request by token: `backend/src/handlers/logs.rs:1763`
- get request via public collection token: `backend/src/handlers/logs.rs:1817`

Public responses remove `user_api_key` before return.

## 9. Playground APIs

Defined in `backend/src/handlers/playground.rs`.

Key endpoints:

- generate temp key: `generate_playground_key` (`backend/src/handlers/playground.rs:145`)
- mod code generation: `generate_mod_code` (`backend/src/handlers/playground.rs:258`)
- mod upload proxy: `upload_mod` (`backend/src/handlers/playground.rs:930`)
- inference proxy: `run_inference` (`backend/src/handlers/playground.rs:1080`)
- feature extract/analyze proxies: `extract_features` (`backend/src/handlers/playground.rs:1283`), `analyze_features` (`backend/src/handlers/playground.rs:1424`)

`analyze_features` has per-key in-memory rate limiting (5 req / 60s) implemented at `backend/src/handlers/playground.rs:20-47`.

### 9.1 Runtime Path for `/playground` (MAX + Sidecar SAE)

`run_inference` resolves model endpoints from env (`ModelEndpoints::from_env`) and forwards to OpenAI-compatible chat:

- endpoint routing: `PLAYGROUND_QWEN_14B_URL` / `PLAYGROUND_LLAMA_8B_URL` (`backend/src/handlers/playground.rs:59-70`)
- target path: `POST {endpoint}/v1/chat/completions` (`backend/src/handlers/playground.rs:1123`)

This path is the base Playground runtime and is distinct from Activation Explorer. SAE behavior for this path is post-hoc sidecar calls:

- `extract_features` forwards to `{PLAYGROUND_SAE_URL}/extract_features` (`backend/src/handlers/playground.rs:1321`)
- `analyze_features` forwards to `{PLAYGROUND_SAE_URL}/analyze_features` (`backend/src/handlers/playground.rs:1473`)

## 10. Activation Explorer API

Defined in `backend/src/handlers/activation_explorer.rs`.

Primary flow (`run_activation`, `backend/src/handlers/activation_explorer.rs:393`):

1. validate request bounds (`backend/src/handlers/activation_explorer.rs:397-453`)
2. call HF inference service (`backend/src/handlers/activation_explorer.rs:481-503`)
3. derive row + top-feature previews from timeline (`backend/src/handlers/activation_explorer.rs:616`, `backend/src/handlers/activation_explorer.rs:629`)
4. persist metadata/index row (`backend/src/handlers/activation_explorer.rs:667`)
5. persist preview payload (`backend/src/handlers/activation_explorer.rs:712`)

Activation Explorer uses a separate runtime path from base Playground:

- HF endpoint base from `PLAYGROUND_ACTIVATIONS_HF_URL` (`backend/src/handlers/activation_explorer.rs:471`)
- generation target is `{HF_BASE}/hf/generate` (`backend/src/handlers/activation_explorer.rs:482`)
- request includes inline SAE fields (`backend/src/handlers/activation_explorer.rs:491-500`)

Query endpoints:

- list runs: `backend/src/handlers/activation_explorer.rs:887`
- summary: `backend/src/handlers/activation_explorer.rs:990`
- rows: `backend/src/handlers/activation_explorer.rs:1049`
- top features: `backend/src/handlers/activation_explorer.rs:1096`
- health: `backend/src/handlers/activation_explorer.rs:1168`

`feature-deltas` is currently not implemented (returns 501): `backend/src/handlers/activation_explorer.rs:1084-1094`.

Health payload includes `sae_service_reachable` and compatibility alias `sae_reachable` (`backend/src/handlers/activation_explorer.rs:1224+`).

## 11. Database Schema

## 11.1 Core Trace Tables

Created in `backend/migrations/0001_new_schema.sql`:

- enums: `event_type`, `action_type`, `log_level` (`backend/migrations/0001_new_schema.sql:29-43`)
- `requests` (`backend/migrations/0001_new_schema.sql:49`)
- `events` (`backend/migrations/0001_new_schema.sql:70`)
- `mod_calls` (`backend/migrations/0001_new_schema.sql:117`)
- `mod_logs` (`backend/migrations/0001_new_schema.sql:147`)
- `actions` (`backend/migrations/0001_new_schema.sql:165`)

Relationship shape:

- `requests (request_id)` -> `events (request_id)`
- `events (id)` -> `mod_calls (event_id)`
- `mod_calls (id)` -> `mod_logs (mod_call_id)` and `actions (mod_call_id)`

## 11.2 Request Extensions

`backend/migrations/0002_add_request_fields.sql:3-9` adds:

- `user_prompt`, `user_prompt_token_ids`
- `active_mod_name`
- `final_token_ids`, `final_text`
- `inference_stats`

## 11.3 Activation Explorer Storage

- index table: `activation_run_index` (`backend/migrations/0013_add_activation_run_index.sql:7`)
- preview/source table: `activation_run_previews` (`backend/migrations/0014_add_activation_run_previews.sql:24`)

`activation_run_previews.feature_timeline` is expected as JSON timeline entries documented in migration comments (`backend/migrations/0014_add_activation_run_previews.sql:8-20`).

## 12. Configuration

`backend/.env.example`:

- server: `APP_HOST`, `APP_PORT`
- database: `DATABASE_URL`
- playground admin + model endpoints:
  - `PLAYGROUND_ADMIN_KEY`
  - `PLAYGROUND_QWEN_14B_URL`
  - `PLAYGROUND_LLAMA_8B_URL`
- activation services:
  - `PLAYGROUND_ACTIVATIONS_HF_URL`
  - `PLAYGROUND_SAE_URL`

## 13. Known Integration Notes

- Activation health keeps both SAE field names for compatibility:
  - frontend type: `frontend/src/lib/api.ts:1062+`
  - backend payload: `backend/src/handlers/activation_explorer.rs:1224+`

## 14. Local Usage

```bash
cd backend
cp .env.example .env
./run_migration.sh
cargo run
```

Health check:

```bash
curl http://127.0.0.1:6767/healthz
```
