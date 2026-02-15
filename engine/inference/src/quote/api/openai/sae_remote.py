"""
Modal deployment for the standalone SAE analysis server.

Lightweight deployment (no MAX Engine / modular) that runs
a HuggingFace Llama 3.1 8B model + SAE for feature extraction
and Claude-powered analysis.
"""

import os

import modal

cuda_version = "12.8.0"
flavor = "cudnn-devel"
operating_sys = "ubuntu24.04"
tag = f"{cuda_version}-{flavor}-{operating_sys}"

image = (
    modal.Image.from_registry(f"nvidia/cuda:{tag}", add_python="3.13")
    .entrypoint([])
    .uv_pip_install(
        "sae-lens",
        "transformers",
        "anthropic",
        "httpx",
        "torch",
        "fastapi",
        "accelerate",
        "hf_transfer",
    )
    .env(
        {
            "HF_HUB_ENABLE_HF_TRANSFER": "1",
            "HF_HOME": "/models/hf",
            "HF_HUB_CACHE": "/models/hf/hub",
        }
    )
    .add_local_python_source(
        "quote.api",
        "quote.interp",
        "quote.interpretability",
        "quote.sae_server",
    )
)

app = modal.App("sae-analysis")
MINUTES = 60

models_vol = modal.Volume.from_name("models", create_if_missing=True)
sae_secret = modal.Secret.from_name("sae-analysis")


@app.function(
    image=image,
    gpu="A10G",
    secrets=[sae_secret],
    volumes={"/models": models_vol},
    min_containers=0,
    max_containers=1,
    scaledown_window=30 * MINUTES,
    timeout=20 * MINUTES,
)
@modal.asgi_app()
@modal.concurrent(max_inputs=5)
def sae_http_app():
    from quote.api.sae_server import create_sae_app

    return create_sae_app()
