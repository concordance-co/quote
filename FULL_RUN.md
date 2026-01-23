# Full Release Dry Run

This document walks through publishing Concordance artifacts (Docker images +
Python wheels) and verifying the workflow from scratch on a clean
workstation. Use it as a dress rehearsal before cutting a production release.

---

## 1. Pick a version

1. Choose a SemVer, e.g. `0.3.0`.
2. Update the repo root `VERSION` file.
3. Update `versions.toml`:

   ```toml
   release_version = "0.3.0"

   [cli]
   package = "concord-cli"
   version = "0.3.0"

   [engine]
   package = "quote"
   version = "0.3.0"

   [sdk]
   package = "concord-sdk"
   version = "0.3.0"

   [images]
   backend = "ghcr.io/<org>/concord-backend:0.3.0"
   frontend = "ghcr.io/<org>/concord-frontend:0.3.0"
   ```
4. Rebuild the CLI and engine wheels so they carry the new version strings.
5. Commit + tag the repo (e.g. `git tag v0.3.0`).

---

## 2. Publish Python artifacts

Build wheels (already done if you followed step 1) then upload:

- **TestPyPI** (recommended for dry runs):

  ```bash
  uv publish --index-url https://test.pypi.org/legacy/ --token <TEST_PYPI_TOKEN>
  ```

- **Alternative**: host the wheels yourself (e.g. GitHub Release, S3). You’ll
  need URLs later for `concord engine install --wheel`.

Artifacts to publish:

| Package       | Wheel path                                |
| ------------- | ----------------------------------------- |
| `concord-cli` | `cli/dist/concord_cli-0.3.0-*.whl`        |
| `quote`       | `engine/dist/quote-0.3.0-*.whl`           |
| `concord-sdk` | `engine/sdk/dist/concord_sdk-0.3.0-*.whl` *(if shipping)* |

---

## 3. Publish Docker images

```bash
# Build with release tag
cd backend
docker build -t ghcr.io/<org>/concord-backend:0.3.0 .

cd ../frontend
docker build -t ghcr.io/<org>/concord-frontend:0.3.0 .

# Push to GHCR (or your registry)
docker login ghcr.io
docker push ghcr.io/<org>/concord-backend:0.3.0
docker push ghcr.io/<org>/concord-frontend:0.3.0
```

No engine image required—the engine runs from the published wheel.

---

## 4. Fresh install smoke test

On a clean machine/director​y:

```bash
uv tool install --index-url https://test.pypi.org/simple/ concord-cli==0.3.0
mkdir concord-demo && cd concord-demo
concord init
```

Edit the generated `.env`:

```env
CONCORD_BACKEND_IMAGE=ghcr.io/<org>/concord-backend:0.3.0
CONCORD_FRONTEND_IMAGE=ghcr.io/<org>/concord-frontend:0.3.0
CONCORD_MODEL_ID=modularai/Llama-3.1-8B-Instruct-GGUF
HUGGINGFACE_HUB_TOKEN=<your-hf-token>
```

Bring services online:

```bash
concord up                       # backend + frontend via Docker
concord engine install --wheel https://example.com/quote-0.3.0.whl
concord engine serve             # runs quote.server.openai.local from the venv
```

Validation checklist:

- `curl http://localhost:6767/healthz` → backend OK.
- `curl http://localhost:8000/healthz` → engine OK (after initial warm-up).
- Visit `http://localhost:5173` for the frontend.

Kill services when done:

```bash
# Stop the native engine (Ctrl+C or `pkill -f quote.server.openai.local`)
concord down --volumes            # optional: removes Docker volumes
```

---

## 5. Promote to production

Once the dry run succeeds:

1. Swap TestPyPI for PyPI in `uv publish` (new token).
2. Push Docker images to the prod registry/namespace.
3. Update `versions.toml` in the main branch with the release version and image tags.
4. Create a GitHub Release attaching the CLI/engine wheels (if hosting there).

---

## Notes & Tips

- Engine caches (HF weights, MAX compilation) land in the user’s standard cache
  directories when `concord engine serve` runs; the first boot is slow, later
  runs are fast.
- `concord engine install` stores virtualenvs under
  `~/.cache/concord/engine/<version>`. Delete the folder to force a reinstall.
- If you need to bundle the SDK for users, publish it to PyPI and update
  documentation; the CLI no longer handles SDK installation.

---

Happy releasing!
