## Variables
# Load optional per-user server config (.servers)
-include .servers

# Prompt and tokens defaults
P ?= Say hi
T ?= 64

# Optional explicit overrides (legacy)
BASE ?=
PUBLISH_URL ?=

# Preferred named bases (set once in .servers)
OPENAI_BASE ?=

## Local servers
openai-local:
	uv run -m quote.server.openai.local --host 0.0.0.0 --port 8000

## Remote servers (Modal)

openai-remote:
	modal serve src/quote/server/openai/remote.py

## Health checks
health-local-openai:
	uv run src/quote/server/router.py --mode local-openai --action health

health-remote-openai:
	uv run src/quote/server/router.py --mode remote-openai --action health --base $(OPENAI_BASE)

## Generate
gen-local-openai:
	uv run src/quote/server/router.py --mode local-openai --action generate --prompt "$(P)" --max_tokens $(T)

gen-local-openai-stream:
	uv run src/quote/server/router.py --mode local-openai --action generate --prompt "$(P)" --max_tokens $(T) --stream

gen-remote-openai:
	uv run src/quote/server/router.py --mode remote-openai --action generate --base $(OPENAI_BASE) --prompt "$(P)" --max_tokens $(T)

gen-remote-openai-stream:
	uv run src/quote/server/router.py --mode remote-openai --action generate --base $(OPENAI_BASE) --prompt "$(P)" --max_tokens $(T) --stream

## Publish hot-swap (remote only)
publish-remote-openai:
	uv run src/quote/server/router.py --mode remote-openai --action publish-exec --base $(OPENAI_BASE) --file src/quote/hot/execute_impl.py

## Hot loop selection (local)
use-vanilla:
	@# Backup current execute_impl.py if it differs from target
	@if ! cmp -s src/quote/hot/execute_impl.py src/quote/hot/vanilla_inference.py; then \
	  ts=$$(date +%Y%m%d-%H%M%S); \
	  mkdir -p src/quote/hot/backups; \
	  cp src/quote/hot/execute_impl.py src/quote/hot/backups/execute_impl.backup.$$ts.py; \
	  echo "Backed up to src/quote/hot/backups/execute_impl.backup.$$ts.py"; \
	fi
	cp src/quote/hot/vanilla_inference.py src/quote/hot/execute_impl.py

use-mod:
	@# Backup current execute_impl.py if it differs from target
	@if ! cmp -s src/quote/hot/execute_impl.py src/quote/hot/mod_inference.py; then \
	  ts=$$(date +%Y%m%d-%H%M%S); \
	  mkdir -p src/quote/hot/backups; \
	  cp src/quote/hot/execute_impl.py src/quote/hot/backups/execute_impl.backup.$$ts.py; \
	  echo "Backed up to src/quote/hot/backups/execute_impl.backup.$$ts.py"; \
	fi
	cp src/quote/hot/mod_inference.py src/quote/hot/execute_impl.py

## Helpers to persist or inspect local edits
save-mod:
	cp src/quote/hot/execute_impl.py src/quote/hot/mod_inference.py
	@echo "Saved current execute_impl.py to mod_inference.py"

diff-mod:
	@diff -u src/quote/hot/mod_inference.py src/quote/hot/execute_impl.py || true

## Restore last/specified backup into execute_impl.py
use-backup:
	@f=$${FILE:-$$(ls -1t src/quote/hot/backups/execute_impl.backup.*.py 2>/dev/null | head -n1)}; \
	if [ -z "$$f" ]; then \
	  echo "No backup found. Pass FILE=path or create a backup by switching loops."; \
	  exit 1; \
	fi; \
	if [ ! -f "$$f" ]; then \
	  echo "Backup file not found: $$f"; \
	  exit 1; \
	fi; \
	cp "$$f" src/quote/hot/execute_impl.py; \
	echo "Restored $$f -> src/quote/hot/execute_impl.py"

## Publish specific loop (remote)
publish-remote-openai-vanilla:
	uv run src/quote/server/router.py --mode remote-openai --action publish-exec --base $(OPENAI_BASE) --file src/quote/hot/vanilla_inference.py

publish-remote-openai-mod:
	uv run src/quote/server/router.py --mode remote-openai --action publish-exec --base $(OPENAI_BASE) --file src/quote/hot/mod_inference.py

test:
	uv run pytest
