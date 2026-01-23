# Build Test

Run everything from the repo root unless a step tells you to `cd` elsewhere. This flow rebuilds the wheels, images, and then exercises them from a scratch directory.

1. Build the Python wheels (CLI, engine, SDK) so `dist/` contents are fresh:
   ```bash
   rm -rf cli/dist engine/dist engine/sdk/dist
   UV_CACHE_DIR=.uv-cache uv build cli
   UV_CACHE_DIR=.uv-cache uv build engine
   UV_CACHE_DIR=.uv-cache uv build engine/sdk
   ```

2. Build the Docker images with a disposable tag to ensure they still compile:
   ```bash
   docker build -t concord-backend:test backend
   docker build -t concord-frontend:test frontend
   ```

3. Stage a clean test workspace that has the built wheels on hand:
   ```bash
   SANDBOX=/tmp/concord-build-test
   rm -rf "${SANDBOX}"
   mkdir -p "${SANDBOX}"
   cp cli/dist/*.whl engine/dist/*.whl engine/sdk/dist/*.whl "${SANDBOX}/"
   cd "${SANDBOX}"
   uv venv .venv
   source .venv/bin/activate
   uv pip install ./concord_cli-*.whl ./quote_mod_sdk-*.whl
   ```

4. Spin up the CLI project using the locally built Docker images:
   ```bash
   concord init
   python - <<'PY'
   from pathlib import Path
   env_path = Path(".env")
   updates = {
       "CONCORD_BACKEND_IMAGE": "concord-backend:test",
       "CONCORD_FRONTEND_IMAGE": "concord-frontend:test",
   }
   lines = env_path.read_text().splitlines()
   written = []
   for line in lines:
       if "=" in line:
           key, _ = line.split("=", 1)
           if key in updates:
               line = f"{key}={updates.pop(key)}"
       written.append(line)
   for key, value in updates.items():
       written.append(f"{key}={value}")
   env_path.write_text("\n".join(written) + "\n")
   PY
   concord up
   concord status
   ```

   If you plan to run step 6, fill in `HUGGINGFACE_HUB_TOKEN` (and the model ID you want) in `.env` before continuing.

5. Install the engine wheel via the CLI (this seeds the managed virtualenv so `concord engine serve` can run later):
   ```bash
   concord engine install --wheel "${SANDBOX}"/quote-*.whl
   ```

6. (Optional) If you have a valid Hugging Face token in `.env`, start the engine and probe the stack:
   ```bash
   concord engine serve --host 127.0.0.1 --port 8000 &
   ENGINE_PID=$!
   sleep 10
   curl -f http://localhost:6767/healthz
   curl -f http://localhost:8000/healthz
   kill "${ENGINE_PID}"
   ```

7. Tear down the environment when done:
   ```bash
   concord down --volumes
   deactivate
   cd -
   ```

If any step fails, capture the command output before re-running so we can adjust the build or docs.
