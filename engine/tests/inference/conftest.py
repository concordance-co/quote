from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Iterable
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


def _install_dotenv_stub() -> None:
    if "dotenv" in sys.modules:
        return
    dotenv = types.ModuleType("dotenv")

    def load_dotenv(*_args: Any, **_kwargs: Any) -> None:
        return None

    dotenv.load_dotenv = load_dotenv  # type: ignore[attr-defined]
    sys.modules["dotenv"] = dotenv


def _install_max_stubs() -> None:
    # Overwrite any real max modules so tests avoid heavy dependencies.
    for name in list(sys.modules):
        if name == "max" or name.startswith("max."):
            sys.modules.pop(name, None)

    max_pkg = types.ModuleType("max")
    sys.modules["max"] = max_pkg

    driver = types.ModuleType("max.driver")

    class Tensor:
        def __init__(self, value: Any | None = None) -> None:
            self.value = value

        def to(self, _device: Any) -> "Tensor":
            return self

        @classmethod
        def from_numpy(cls, array: Any) -> "Tensor":
            return cls(array)

    driver.Tensor = Tensor  # type: ignore[attr-defined]
    sys.modules["max.driver"] = driver
    max_pkg.driver = driver  # type: ignore[attr-defined]

    dtype = types.ModuleType("max.dtype")

    class DType:  # pragma: no cover - placeholder
        pass

    dtype.DType = DType  # type: ignore[attr-defined]
    sys.modules["max.dtype"] = dtype
    max_pkg.dtype = dtype  # type: ignore[attr-defined]

    interfaces = types.ModuleType("max.interfaces")

    class PipelineTask:  # pragma: no cover - placeholder
        TEXT_GENERATION = "text_generation"

    class SamplingParams:
        def __init__(self, **kwargs: Any) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    class TextGenerationRequest:
        def __init__(self, **kwargs: Any) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    class TextGenerationRequestMessage:
        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload

    class TextGenerationInputs:
        def __init__(self, batches: Iterable[dict[str, Any]] | None = None, num_steps: int = 0) -> None:
            self.batches = list(batches or [])
            merged: dict[str, Any] = {}
            for mapping in self.batches:
                merged.update(mapping)
            self.batch = merged
            self.num_steps = num_steps

    interfaces.PipelineTask = PipelineTask  # type: ignore[attr-defined]
    interfaces.SamplingParams = SamplingParams  # type: ignore[attr-defined]
    interfaces.TextGenerationRequest = TextGenerationRequest  # type: ignore[attr-defined]
    interfaces.TextGenerationRequestMessage = TextGenerationRequestMessage  # type: ignore[attr-defined]
    interfaces.TextGenerationInputs = TextGenerationInputs  # type: ignore[attr-defined]
    sys.modules["max.interfaces"] = interfaces
    max_pkg.interfaces = interfaces  # type: ignore[attr-defined]

    pipelines_lib = types.ModuleType("max.pipelines.lib")

    class PipelineConfig:
        def __init__(self, **kwargs: Any) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    class PipelineModel:  # pragma: no cover - placeholder
        pass

    class SpeechTokenGenerationPipeline:  # pragma: no cover - placeholder
        pass

    class RepoType:  # pragma: no cover - placeholder
        pass

    class LoRAManager:  # pragma: no cover - placeholder
        pass

    class KVCacheConfig:  # pragma: no cover - placeholder
        pass

    def download_weight_files(*_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - placeholder
        return None

    def token_sampler(*_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - placeholder
        return None

    class ModelInputs:  # pragma: no cover - placeholder
        pass

    class ModelOutputs:  # pragma: no cover - placeholder
        def __init__(self, logits: Any | None = None):
            self.logits = logits

    class _TokenizerStub:
        eos = 0

        def apply_chat_template(self, messages: Iterable[Any], *_args: Any) -> str:
            parts: list[str] = []
            for message in messages:
                if hasattr(message, "payload") and isinstance(message.payload, dict):
                    parts.append(str(message.payload.get("content", "")))
                elif isinstance(message, dict):
                    parts.append(str(message.get("content", "")))
            return "\n".join(parts)

        async def new_context(self, request: Any) -> Any:
            return SimpleNamespace(request_id=getattr(request, "request_id", "req"))

        async def decode(self, tokens: Iterable[int]) -> str:
            try:
                return "".join(chr(int(t)) for t in tokens)
            except Exception:
                return str(list(tokens))

    class _Registry:
        def retrieve_factory(self, _cfg: Any, _task: Any = None) -> tuple[Any, Any]:
            def factory():
                return SimpleNamespace(
                    _weight_adapters={},
                    _pipeline_model=PipelineModel(),
                    _pipeline_config=SimpleNamespace(model_config=SimpleNamespace(device_specs=None)),
                )

            return _TokenizerStub(), factory

    pipelines_lib.PIPELINE_REGISTRY = _Registry()  # type: ignore[attr-defined]
    pipelines_lib.PipelineConfig = PipelineConfig  # type: ignore[attr-defined]
    pipelines_lib.PipelineModel = PipelineModel  # type: ignore[attr-defined]
    pipelines_lib.SpeechTokenGenerationPipeline = SpeechTokenGenerationPipeline  # type: ignore[attr-defined]
    pipelines_lib.TextTokenizer = _TokenizerStub  # type: ignore[attr-defined]
    pipelines_lib.RepoType = RepoType  # type: ignore[attr-defined]
    pipelines_lib.download_weight_files = download_weight_files  # type: ignore[attr-defined]
    pipelines_lib.LoRAManager = LoRAManager  # type: ignore[attr-defined]
    pipelines_lib.KVCacheConfig = KVCacheConfig  # type: ignore[attr-defined]
    pipelines_lib.token_sampler = token_sampler  # type: ignore[attr-defined]
    pipelines_lib.ModelInputs = ModelInputs  # type: ignore[attr-defined]
    pipelines_lib.ModelOutputs = ModelOutputs  # type: ignore[attr-defined]
    sys.modules["max.pipelines.lib"] = pipelines_lib
    max_pkg.pipelines = SimpleNamespace(lib=pipelines_lib)  # type: ignore[attr-defined]

    pipelines_tokenizer = types.ModuleType("max.pipelines.lib.tokenizer")

    def load_tokenizer(*_args: Any, **_kwargs: Any) -> _TokenizerStub:
        return _TokenizerStub()

    pipelines_tokenizer.load_tokenizer = load_tokenizer  # type: ignore[attr-defined]
    sys.modules["max.pipelines.lib.tokenizer"] = pipelines_tokenizer


    serve_llm = types.ModuleType("max.serve.pipelines.llm")

    class AudioGeneratorPipeline:  # pragma: no cover - placeholder
        pass

    serve_llm.AudioGeneratorPipeline = AudioGeneratorPipeline  # type: ignore[attr-defined]
    sys.modules["max.serve.pipelines.llm"] = serve_llm
    max_pkg.serve = SimpleNamespace(pipelines=SimpleNamespace(llm=serve_llm))  # type: ignore[attr-defined]

    kv_cache = types.ModuleType("max.nn.kv_cache")

    class KVCacheInputsSequence:  # pragma: no cover - placeholder
        pass

    class KVCacheManager:  # pragma: no cover - placeholder
        pass

    class PagedKVCacheManager:  # pragma: no cover - placeholder
        pass

    def infer_optimal_batch_size(*_args: Any, **_kwargs: Any) -> int:
        return 1

    kv_cache.KVCacheInputsSequence = KVCacheInputsSequence  # type: ignore[attr-defined]
    kv_cache.KVCacheManager = KVCacheManager  # type: ignore[attr-defined]
    kv_cache.PagedKVCacheManager = PagedKVCacheManager  # type: ignore[attr-defined]
    kv_cache.infer_optimal_batch_size = infer_optimal_batch_size  # type: ignore[attr-defined]
    sys.modules["max.nn.kv_cache"] = kv_cache
    max_pkg.nn = SimpleNamespace(kv_cache=kv_cache)  # type: ignore[attr-defined]


def _install_text_pipeline_stub() -> None:
    module_name = "quote.pipelines.text_gen_pipeline"
    if module_name in sys.modules:
        return

    module = types.ModuleType(module_name)

    class _TokenizerShim:
        eos = 0

        def apply_chat_template(self, messages: Iterable[Any], *_args: Any) -> str:
            parts: list[str] = []
            for message in messages:
                if hasattr(message, "payload") and isinstance(message.payload, dict):
                    parts.append(str(message.payload.get("content", "")))
                elif isinstance(message, dict):
                    parts.append(str(message.get("content", "")))
            return "\n".join(parts)

        async def new_context(self, request: Any) -> Any:
            return SimpleNamespace(request_id=getattr(request, "request_id", "req"))

        async def decode(self, tokens: Iterable[int]) -> str:
            try:
                return "".join(chr(int(t)) for t in tokens)
            except Exception:
                return str(list(tokens))

    class TextGenerationPipeline:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.tokenizer = _TokenizerShim()
            self.mod_manager = SimpleNamespace(mods=[])
            self.batch_info_output_fname = None
            self._devices = [SimpleNamespace()]
            self._pipeline_config = SimpleNamespace(sampling_config=SimpleNamespace(do_penalties=False))

        def _maybe_sort_loras(self, batch: dict[str, Any]) -> dict[str, Any]:
            return batch

        def prepare_batch(self, context_batch: Iterable[Any], num_steps: int):
            return SimpleNamespace(), num_steps, None

        def _record_batch_info(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def _build_min_tokens_masks(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def _check_need_penalties(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def _build_token_frequency_csr(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def release(self, *_args: Any, **_kwargs: Any) -> None:
            return None

    module.TextGenerationPipeline = TextGenerationPipeline  # type: ignore[attr-defined]
    sys.modules[module_name] = module



_install_dotenv_stub()
_install_max_stubs()
_install_text_pipeline_stub()

from quote.mods.manager import ModManager


class FakeContext:
    def __init__(self, request_id: str) -> None:
        self.request_id = request_id
        self.current_length = 0
        self.log_probabilities = None
        self.log_probabilities_echo = None
        self.is_done = False

    def update(self, **_kwargs: Any) -> None:
        return None

    def to_generation_output(self) -> SimpleNamespace:
        return SimpleNamespace(tokens=[])


class FakeTokenizer:
    def __init__(self) -> None:
        self._contexts: dict[str, FakeContext] = {}

    def apply_chat_template(self, messages: Iterable[Any], *_args: Any) -> str:
        parts: list[str] = []
        for message in messages:
            if hasattr(message, "payload") and isinstance(message.payload, dict):
                parts.append(str(message.payload.get("content", "")))
            elif isinstance(message, dict):
                parts.append(str(message.get("content", "")))
        return "\n".join(parts)

    async def new_context(self, request: Any) -> FakeContext:
        ctx = FakeContext(getattr(request, "request_id", "req"))
        self._contexts[ctx.request_id] = ctx
        return ctx

    async def decode(self, tokens: Iterable[int]) -> str:
        try:
            return "".join(chr(int(t)) for t in tokens)
        except Exception:
            return str(list(tokens))


class FakePipeline:
    def __init__(self) -> None:
        self.default_text = "fake-response"
        self.mod_manager = ModManager([])
        self.releases: list[str] = []
        self.calls: list[Any] = []
        self.last_mods: list[Any] | None = None

    def set_response_text(self, text: str) -> None:
        self.default_text = text

    def execute(self, inputs: Any) -> dict[str, SimpleNamespace]:
        self.calls.append(inputs)
        self.last_mods = list(getattr(self.mod_manager, "mods", []))
        outputs: dict[str, SimpleNamespace] = {}
        for request_id in getattr(inputs, "batch", {}):
            tokens = [ord(ch) for ch in self.default_text]
            outputs[request_id] = SimpleNamespace(tokens=tokens)
        return outputs

    def release(self, request_id: str) -> None:
        self.releases.append(request_id)


class FakeExecuteModule:
    def execute(self, pipeline: FakePipeline, inputs: Any) -> dict[str, SimpleNamespace]:
        return pipeline.execute(inputs)


@dataclass
class FakeServerComponents:
    tokenizer: FakeTokenizer = field(default_factory=FakeTokenizer)
    pipeline: FakePipeline = field(default_factory=FakePipeline)
    exec_module: FakeExecuteModule = field(default_factory=FakeExecuteModule)
    model_id: str = "fake-org/fake-model"
    exec_path_calls: list[Any] = field(default_factory=list)

    def set_response_text(self, text: str) -> None:
        self.pipeline.set_response_text(text)


@pytest.fixture
def server_app_harness(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    from importlib import import_module

    components = FakeServerComponents()
    try:
        components.pipeline.mod_manager.set_tokenizer(components.tokenizer)
    except Exception:
        pass

    core = import_module("quote.server.core")
    dev_local = import_module("quote.server.dev.local")
    openai_local = import_module("quote.server.openai.local")

    def fake_init_pipeline(_model_id: str | None = None) -> tuple[FakeTokenizer, FakePipeline, str]:
        return components.tokenizer, components.pipeline, components.model_id

    def fake_make_maybe_reload_exec(_state: dict[str, Any]) -> Any:
        return lambda: components.exec_module

    def fake_write_default_exec_if_missing(path: Any) -> None:
        components.exec_path_calls.append(path)

    class DummyLogger:
        def __init__(self, request_id: str) -> None:
            self.request_id = request_id

        def emit_request_start(self, **_kwargs: Any) -> None:
            return None

        def emit_request_end(self, **_kwargs: Any) -> None:
            return None

        def close(self) -> None:
            return None

    for module in (core, dev_local, openai_local):
        monkeypatch.setattr(module, "init_pipeline", fake_init_pipeline, raising=False)
        monkeypatch.setattr(module, "make_maybe_reload_exec", fake_make_maybe_reload_exec, raising=False)
        monkeypatch.setattr(module, "write_default_exec_if_missing", fake_write_default_exec_if_missing, raising=False)

    def _dummy_get_accumulator(request_id: str) -> DummyLogger:
        return DummyLogger(request_id)

    for module in (dev_local, openai_local):
        monkeypatch.setattr(module, "get_accumulator", _dummy_get_accumulator, raising=False)

    return SimpleNamespace(components=components, dev=dev_local, openai=openai_local)
