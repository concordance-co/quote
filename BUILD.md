Gotcha — here are the broad strokes, clean enough to hand to a coding agent without repo-specific assumptions.

# Shipping Plan (Private mono → Public artifacts)

## What you ship

* **Docker images (public):** backend, engine, frontend — each tagged with the same SemVer.
* **Python packages (public):**

  * `concord-sdk` (users add to their app)
  * `concord-cli` (tiny orchestrator users install as a tool)

Monorepo stays private. Users never build from source; they pull artifacts.

---

## Versioning & pins

* Single **SemVer** for the whole product (e.g., `VERSION` file).
* A small **`versions.toml`** that pins:

  * SDK version
  * Image names + tags
  * Default ports (optional)
* Release bumps update both.

---

## Release pipeline (on git tag `vX.Y.Z`)

1. **Build & push Docker images** to GHCR:

   * `concord-backend:X.Y.Z`
   * `concord-engine:X.Y.Z`
   * `concord-frontend:X.Y.Z`
   * (prefer multi-arch: amd64 + arm64)
2. **Publish PyPI packages:**

   * `concord-sdk == X.Y.Z`
   * `concord-cli == X.Y.Z` (includes `versions.toml` as package data)
3. **Create GitHub Release** (notes, checksums if you add them later).

That’s it. No user needs repo access.

---

## CLI responsibilities (thin, user-facing)

* **Install:** `uv tool install concord-cli==X.Y.Z`
* **Commands (MVP):**

  * `init` → generate `.env` + `docker-compose.user.yml` using `versions.toml`.
  * `up` / `down` / `status` → wrap `docker compose` with the generated file.
  * `sdk-add` → run `uv add concord-sdk==<pinned>` in the user’s project.
* **Profiles:** not required; default uses published images.
* **Must not:** build source or require repo.

---

## SDK scope (minimal contract)

* Small, stable public API for writing “mods”.
* Version equals the product SemVer; changelog calls out breaking changes.
* Published to PyPI; no private indexes needed (Option A).

---

## Images (broad requirements)

* **Backend:** multi-stage Dockerfile, small final image, exposes API + `/healthz`.
* **Engine:** Python slim base; install deps; exposes API + `/healthz`.
* **Frontend:** build → serve static with Nginx/Caddy.
* Add simple health checks so `docker compose` sequencing is reliable.

---

## Dev vs. user flows (keep dev unchanged)

* **Developers:** keep existing run scripts and `cd` dance (no CLI required).
* **Users:** install CLI → `init` → `up` → `sdk-add` — no builds, just pulls.

---

## Security & hygiene (lightweight)

* Never mutate a released tag (`X.Y.Z` immutable).
* Optionally keep a moving `:stable` tag pointing to the latest.
* Add `/healthz` endpoints and a basic DB schema version check in backend.
* (Later) SBOM/provenance/signing, if your customers care.

---

## Minimal docs users will see

1. `uv tool install concord-cli==X.Y.Z`
2. `mkdir my-project && cd my-project`
3. `concord init`
4. `concord up`
5. `concord sdk-add`
6. Open `http://localhost:<frontend_port>`

We will also want:
1. `concord serve engine` -- serves the openai compatible server
2. `concord serve frontend` -- serves the frontend
3. `concord serve backend` -- serves the backend
4. `concord register_mod' -- basically the same as engine/scripts/register_mod

---

## Hand-off checklist for the coding agent

* Create `VERSION` and `versions.toml` at repo root.
* Add a tag-triggered workflow that:

  * builds & pushes three images to GHCR (multi-arch),
  * publishes `concord-sdk` and `concord-cli` to PyPI,
  * creates a GitHub Release.
* Implement `concord-cli` with commands: `init | up | down | status | sdk-add`.

  * Package `versions.toml` inside the CLI wheel.
* Ensure each service exposes a health endpoint; compose uses those.
* Write a short “Install & Run” section for users exactly as above.

That’s the whole shape. The agent can fill in Dockerfiles, workflow YAML, and CLI code.
