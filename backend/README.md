# Thunder Backend

A Rust-based backend service that powers observability, logging intake, and confidence scoring for the Quote inference stack. The service is built on top of [axum](https://docs.rs/axum) and Postgres.

## Prerequisites
- Rust toolchain (via `rustup`)
- Docker and Docker Compose

## Configuration
Copy the example environment variables before running the service locally or in Docker:

```bash
cp .env.example .env
```

Key variables:
- `APP_HOST` / `APP_PORT`: the bind address for the HTTP server
- `DATABASE_URL`: Postgres connection string (uses `localhost` for local dev, overridden to `postgres` in Docker Compose)

## Running Locally
1. Start Postgres (Docker is the quickest path):
   ```bash
   docker compose up postgres -d
   ```
2. Run the server with cargo:
   ```bash
   cargo run
   ```
3. Hit the health check:
  ```bash
  curl http://127.0.0.1:6767/healthz
  ```


## Running with Docker Compose
Build and launch the full stack:

```bash
docker compose up --build
```

This starts `thunder-backend` (axum server) and `thunder-postgres`. The backend listens on `http://localhost:6767`.

## Deploying to Modal

`deploy.py` supports environment-targeted deploys by app name and secret name.

Environment variables:
- `MODAL_APP_NAME` (default: `thunder-backend`)
- `MODAL_SECRET_NAME` (default: `thunder-db`)

Example: staging deploy with a separate Neon-backed secret:

```bash
cd backend
modal secret create thunder-db-staging DATABASE_URL='postgresql://...'
MODAL_APP_NAME=thunder-backend-staging \
MODAL_SECRET_NAME=thunder-db-staging \
modal deploy deploy.py
```

Example: production deploy:

```bash
cd backend
MODAL_APP_NAME=thunder-backend \
MODAL_SECRET_NAME=thunder-db \
modal deploy deploy.py
```

## Development Notes
- The health endpoint performs a lightweight `SELECT 1` to verify Postgres connectivity.
- Logging uses `tracing`; control verbosity via `RUST_LOG` (e.g., `RUST_LOG=debug cargo run`).
- The service exposes `GET /logs`, `GET /logs/:request_id`, and `POST /v1/ingest`. Endpoint semantics and payload examples live in [`docs/API.md`](docs/API.md).
- Additional reference material (API, schema dbml, Quote context) resides in the `docs/` folder.
- `cargo fmt` and `cargo check` are wired in; run them before committing changes.

### Clearing Data Without Dropping the Schema

Use this when you need a clean slate but want to keep the schema and migrations intact:

```bash
# Stop the backend so no writes race the truncate
# Then open a psql shell (adjust to your environment)
docker compose exec postgres psql -U postgres -d thunder

-- Inside psql, run a cascading truncate and reset sequences
TRUNCATE TABLE
  actions,
  step_logit_summaries,
  request_steps,
  requests,
  mod_blocks,
  mods
RESTART IDENTITY CASCADE;
```

Exit `psql`, restart the backend (`cargo run` or `docker compose up --build`), and you’ll be working with an empty database.

For local Postgres instances (no Docker), run the same `TRUNCATE` block inside a `psql` session pointed at your `$DATABASE_URL`.

### Capturing a Schema Snapshot

Generate a `current_schema.sql` file in the repository root. Run one of the commands below from the repo root depending on your Postgres setup:

```bash
# Using Docker Compose (default dev stack)
docker compose exec postgres pg_dump -U postgres -d thunder --schema-only --no-owner --no-privileges > current_schema.sql

# Or with a local Postgres instance
pg_dump "$DATABASE_URL" --schema-only --no-owner --no-privileges > current_schema.sql
```

The redirect overwrites any existing snapshot; rerun the command whenever you need an updated copy.

### API Reference

Endpoint descriptions, request/response schemas, and example payloads are documented in [`docs/API.md`](docs/API.md). The document covers the `GET /logs` feed, the `GET /logs/:request_id` detail view, and the `POST /v1/ingest` contract used by inference services.
