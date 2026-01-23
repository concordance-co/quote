import modal
import os
import subprocess

app = modal.App("thunder-backend")

image = modal.Image.from_dockerfile("dockerfile").env({
    # force a proper bind address for Modal
    "APP_HOST": "0.0.0.0",
    "APP_PORT": "6767",
})

# Secret holds DATABASE_URL (and any other sensitive vars you like)
thunder_secret = modal.Secret.from_name("thunder-db")

def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc

MINUTES = 60
MODAL_CPU = _env_int("MODAL_CPU", 3)
MODAL_MEMORY_MB = _env_int("MODAL_MEMORY_MB", 3000)
MODAL_MIN_CONTAINERS = 0
MODAL_MAX_CONTAINERS = _env_int("MODAL_MAX_CONTAINERS", 1)
MODAL_SCALEDOWN_MINUTES = _env_int("MODAL_SCALEDOWN_MINUTES", 120)

@app.function(
    image=image,
    secrets=[thunder_secret],
    min_containers=MODAL_MIN_CONTAINERS,
    max_containers=MODAL_MAX_CONTAINERS,
    cpu=MODAL_CPU,
    memory=MODAL_MEMORY_MB,
    scaledown_window=max(2, min(3600, MODAL_SCALEDOWN_MINUTES * MINUTES)),
    enable_memory_snapshot=True,
    startup_timeout=300,
)
@modal.web_server(port=6767, startup_timeout=300)
@modal.concurrent(max_inputs=100)
def thunder_server():
    # Start the Rust server. Modal will forward HTTP to port 6767.
    subprocess.Popen(
        ["./thunder"],
        cwd="/app",
        env=dict(os.environ),
    )
