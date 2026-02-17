"""
Standalone Modal deploy for the HF Inference endpoint (activations playground).

Uses quote.runtime.generation for true inline SAE extraction and
quote.backends.huggingface for model management. No MAX/modular dependencies.

    modal deploy src/quote/api/openai/hf_remote.py
"""

import os

import modal

cuda_version = "12.8.0"
flavor = "cudnn-devel"
operating_sys = "ubuntu24.04"
tag = f"{cuda_version}-{flavor}-{operating_sys}"

app = modal.App("hf-inference-staging")
MINUTES = 60

hf_inference_image = (
    modal.Image.from_registry(f"nvidia/cuda:{tag}", add_python="3.13")
    .entrypoint([])
    .uv_pip_install(
        "transformers",
        "torch",
        "fastapi",
        "accelerate",
        "hf_transfer",
        "pydantic",
        "sae-lens",
        "requests",
        "numpy",
    )
    .env(
        {
            "HF_HUB_ENABLE_HF_TRANSFER": "1",
            "HF_HOME": "/models/hf",
            "HF_HUB_CACHE": "/models/hf/hub",
            "HF_TOKEN": os.environ.get("HF_TOKEN", ""),
        }
    )
    .add_local_python_source(
        "quote",
        "shared",
    )
)

models_vol = modal.Volume.from_name("models", create_if_missing=True)


@app.function(
    image=hf_inference_image,
    gpu="A10G",
    volumes={"/models": models_vol},
    min_containers=0,
    max_containers=1,
    scaledown_window=30 * MINUTES,
    timeout=10 * MINUTES,
)
@modal.asgi_app()
@modal.concurrent(max_inputs=5)
def hf_inference_app():
    from quote.api.hf_inference import create_hf_inference_app

    return create_hf_inference_app()
