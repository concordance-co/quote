from max.pipelines.lib import PIPELINE_REGISTRY

_MODELS_ALREADY_REGISTERED = False


def register_all_models() -> None:
    """Imports model architectures, thus registering the architecture in the shared :obj:`~max.pipelines.registry.PipelineRegistry`."""
    global _MODELS_ALREADY_REGISTERED

    if _MODELS_ALREADY_REGISTERED:
        return

    from .gemma3 import gemma3_arch
    from .gemma3multimodal import gemma3_multimodal_arch

    architectures = [
        gemma3_arch,
        gemma3_multimodal_arch,
    ]

    for arch in architectures:
        PIPELINE_REGISTRY.register(arch, allow_override=True)

    _MODELS_ALREADY_REGISTERED = True


__all__ = ["register_all_models"]
