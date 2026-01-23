from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from contextlib import asynccontextmanager
import types as _types
import typing as _typing
from typing import Any

import pytest



# Ensure project root and src are importable
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = PROJECT_ROOT / "src"
INFER_PATH = PROJECT_ROOT / "inference" / "src"
SHARED_PATH = PROJECT_ROOT / "shared" / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
if str(INFER_PATH) not in sys.path:
    sys.path.insert(0, str(INFER_PATH))
if str(SHARED_PATH) not in sys.path:
    sys.path.insert(0, str(SHARED_PATH))


# Import the root tests stubs to avoid heavy MAX deps
# This module installs stubs on import.
try:
    import tests.conftest as root_test_stubs  # noqa: F401
except Exception:
    root_test_stubs = None  # type: ignore[assignment]
else:
    # Patch PIPELINE_REGISTRY stub to accept keyword 'task'
    try:
        _pipelib = sys.modules.get("max.pipelines.lib")
        _registry = getattr(_pipelib, "PIPELINE_REGISTRY", None)
        if _registry is not None:
            _orig_rf = _registry.retrieve_factory
            def _rf(cfg, task=None, **_kw):
                return _orig_rf(cfg, task)
            _registry.retrieve_factory = _rf  # type: ignore[attr-defined]
    except Exception:
        pass


# Ensure missing interface symbols exist for quote.server.openai.local import
interfaces = sys.modules.get("max.interfaces")
if interfaces is None:
    interfaces = _types.ModuleType("max.interfaces")
    sys.modules["max.interfaces"] = interfaces

if not hasattr(interfaces, "PipelineTokenizer"):
    class PipelineTokenizer:  # pragma: no cover - type placeholder
        pass
    interfaces.PipelineTokenizer = PipelineTokenizer  # type: ignore[attr-defined]

if not hasattr(interfaces, "PipelineTask"):
    class PipelineTask:  # pragma: no cover
        TEXT_GENERATION = "text_generation"
    interfaces.PipelineTask = PipelineTask  # type: ignore[attr-defined]

if not hasattr(interfaces, "SamplingParams"):
    class SamplingParams:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    interfaces.SamplingParams = SamplingParams  # type: ignore[attr-defined]

if not hasattr(interfaces, "TextGenerationRequest"):
    class TextGenerationRequest:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    interfaces.TextGenerationRequest = TextGenerationRequest  # type: ignore[attr-defined]
if not hasattr(interfaces, "TextGenerationRequestMessage"):
    class TextGenerationRequestMessage:
        def __init__(self, role=None, content=None):
            self.role = role
            self.content = content
    interfaces.TextGenerationRequestMessage = TextGenerationRequestMessage  # type: ignore[attr-defined]
if not hasattr(interfaces, "TextGenerationInputs"):
    class TextGenerationInputs:
        def __init__(self, batches=None, num_steps: int = 0):
            self.batches = list(batches or [])
            merged = {}
            for mapping in self.batches:
                merged.update(mapping)
            self.batch = merged
            self.num_steps = num_steps
    interfaces.TextGenerationInputs = TextGenerationInputs  # type: ignore[attr-defined]
if not hasattr(interfaces, "InputContext"):
    class InputContext:  # pragma: no cover
        pass
    interfaces.InputContext = InputContext  # type: ignore[attr-defined]
if not hasattr(interfaces, "LogProbabilities"):
    class LogProbabilities:  # pragma: no cover
        token_log_probabilities: list[float] = []
        top_log_probabilities: list[dict[int, float]] = []
    interfaces.LogProbabilities = LogProbabilities  # type: ignore[attr-defined]
if not hasattr(interfaces, "Pipeline"):
    class Pipeline:  # pragma: no cover
        pass
    interfaces.Pipeline = Pipeline  # type: ignore[attr-defined]
if not hasattr(interfaces, "PipelineOutputsDict"):
    PipelineOutputsDict = dict  # type: ignore
    interfaces.PipelineOutputsDict = PipelineOutputsDict  # type: ignore[attr-defined]
if not hasattr(interfaces, "RequestID"):
    interfaces.RequestID = str  # type: ignore[attr-defined]

if not hasattr(interfaces, "TextGenerationRequestFunction"):
    class TextGenerationRequestFunction:
        def __init__(self, name: str, description=None, parameters=None):
            self.name = name
            self.description = description
            self.parameters = parameters or {}
    interfaces.TextGenerationRequestFunction = TextGenerationRequestFunction  # type: ignore[attr-defined]

if not hasattr(interfaces, "TextGenerationRequestTool"):
    class TextGenerationRequestTool:
        def __init__(self, type: str, function=None):
            self.type = type
            self.function = function
    interfaces.TextGenerationRequestTool = TextGenerationRequestTool  # type: ignore[attr-defined]

if not hasattr(interfaces, "TextGenerationOutput"):
    class TextGenerationOutput:  # minimal attributes used by server fallback
        def __init__(self, request_id=None, tokens=None, log_probabilities=None, final_status=None):
            self.request_id = request_id
            self.tokens = list(tokens or [])
            self.log_probabilities = log_probabilities
            self.final_status = final_status
    interfaces.TextGenerationOutput = TextGenerationOutput  # type: ignore[attr-defined]

if not hasattr(interfaces, "GenerationStatus"):
    class GenerationStatus:  # pragma: no cover - minimal sentinel
        CANCELLED = object()
    interfaces.GenerationStatus = GenerationStatus  # type: ignore[attr-defined]

# Additional optional interface placeholders referenced by token_gen_pipeline
for _name in (
    "AudioGenerationRequest",
    "AudioGeneratorOutput",
    "EmbeddingsGenerationOutput",
    "LogProbabilities",
):
    if not hasattr(interfaces, _name):
        setattr(interfaces, _name, type(_name, (), {}))

# Factories type placeholder
if not hasattr(interfaces, "PipelinesFactory"):
    class PipelinesFactory:  # pragma: no cover
        pass
    interfaces.PipelinesFactory = PipelinesFactory  # type: ignore[attr-defined]

# Special case: used in Generic[...] context
interfaces.AudioGeneratorContext = getattr(interfaces, "AudioGeneratorContext", _typing.TypeVar("AudioGeneratorContext"))


# Additional stub modules required by imports
def _ensure_module(name: str):
    m = sys.modules.get(name)
    if m is None:
        m = _types.ModuleType(name)
        sys.modules[name] = m
    return m

# max.profiler
profiler = _ensure_module("max.profiler")
class Tracer:  # pragma: no cover - no-op tracer
    def __init__(self, *_args, **_kwargs):
        pass
def traced(*_args, **_kwargs):  # pragma: no cover - no-op decorator
    def _decorator(fn):
        return fn
    return _decorator
profiler.Tracer = Tracer  # type: ignore[attr-defined]
profiler.traced = traced  # type: ignore[attr-defined]

# max.pipelines.core
pip_core = _ensure_module("max.pipelines.core")
class TextContext:  # pragma: no cover
    pass
pip_core.TextContext = TextContext  # type: ignore[attr-defined]

# max.pipelines.lib stub
pip_lib = _ensure_module("max.pipelines.lib")
class PipelineConfig:  # pragma: no cover
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
class PipelineModel:  # pragma: no cover
    pass
class _TokenizerStub:  # pragma: no cover
    eos = 0
    def apply_chat_template(self, messages, *_args):
        return "\n".join(str(getattr(m, 'content', getattr(m, 'payload', {}))) for m in messages)
pip_lib.TextTokenizer = _TokenizerStub  # type: ignore[attr-defined]
class SpeechTokenGenerationPipeline:  # pragma: no cover
    pass
pip_lib.SpeechTokenGenerationPipeline = SpeechTokenGenerationPipeline  # type: ignore[attr-defined]
class _Registry:  # pragma: no cover
    def retrieve_factory(self, _cfg, task=None):
        def factory():
            return SimpleNamespace(
                _weight_adapters={},
                _pipeline_model=PipelineModel(),
                _pipeline_config=SimpleNamespace(model_config=SimpleNamespace(device_specs=None)),
            )
        return _TokenizerStub(), factory
pip_lib.PIPELINE_REGISTRY = _Registry()  # type: ignore[attr-defined]
pip_lib.PipelineConfig = PipelineConfig  # type: ignore[attr-defined]
pip_lib.PipelineModel = PipelineModel  # type: ignore[attr-defined]
class RepoType:  # pragma: no cover
    pass
pip_lib.RepoType = RepoType  # type: ignore[attr-defined]
def download_weight_files(*_args, **_kwargs):  # pragma: no cover
    return None
pip_lib.download_weight_files = download_weight_files  # type: ignore[attr-defined]
class LoRAManager:  # pragma: no cover
    pass
pip_lib.LoRAManager = LoRAManager  # type: ignore[attr-defined]
class KVCacheConfig:  # pragma: no cover
    pass
pip_lib.KVCacheConfig = KVCacheConfig  # type: ignore[attr-defined]
def token_sampler(*_args, **_kwargs):  # pragma: no cover
    return None
pip_lib.token_sampler = token_sampler  # type: ignore[attr-defined]
class ModelInputs:  # pragma: no cover
    pass
class ModelOutputs:  # pragma: no cover
    def __init__(self, logits: Any | None = None):
        self.logits = logits
pip_lib.ModelInputs = ModelInputs  # type: ignore[attr-defined]
pip_lib.ModelOutputs = ModelOutputs  # type: ignore[attr-defined]

# max.driver
driver = _ensure_module("max.driver")
class Tensor:  # pragma: no cover - minimal tensor
    def __init__(self, *_args, **_kwargs):
        pass
    def to(self, *_args, **_kwargs):
        return self
driver.Tensor = Tensor  # type: ignore[attr-defined]
class Device:  # pragma: no cover
    pass
class CPU:  # pragma: no cover
    pass
class Accelerator:  # pragma: no cover
    pass
driver.Device = Device  # type: ignore[attr-defined]
driver.CPU = CPU  # type: ignore[attr-defined]
driver.Accelerator = Accelerator  # type: ignore[attr-defined]
driver.DLPackArray = object  # type: ignore[attr-defined]
class DeviceSpec:  # pragma: no cover
    pass
def load_devices(*_args, **_kwargs):  # pragma: no cover
    return []
driver.DeviceSpec = DeviceSpec  # type: ignore[attr-defined]
driver.load_devices = load_devices  # type: ignore[attr-defined]

# max.serve.config
serve_config = _ensure_module("max.serve.config")
class Settings:  # pragma: no cover
    pass
serve_config.Settings = Settings  # type: ignore[attr-defined]

# max.serve.pipelines.stop_detection
stop_det = _ensure_module("max.serve.pipelines.stop_detection")
class StopDetector:  # pragma: no cover
    def __init__(self, stop=None):
        self.stop = stop or []
    def step(self, _decoded: str):
        return None
stop_det.StopDetector = StopDetector  # type: ignore[attr-defined]

# max.serve.process_control
proc_ctrl = _ensure_module("max.serve.process_control")
class ProcessMonitor:  # pragma: no cover
    pass
proc_ctrl.ProcessMonitor = ProcessMonitor  # type: ignore[attr-defined]

# max.serve.queue.lora_queue
lora_q = _ensure_module("max.serve.queue.lora_queue")
class LoRAQueue:  # pragma: no cover
    pass
lora_q.LoRAQueue = LoRAQueue  # type: ignore[attr-defined]

# max.serve.scheduler.queues
sched = _ensure_module("max.serve.scheduler.queues")
class EngineQueue:  # pragma: no cover - minimal API
    def __init__(self, *args, **kwargs):
        self.cancel_queue = SimpleNamespace(put_nowait=lambda *_: None)
    async def stream(self, *_args, **_kwargs):
        if False:
            yield None
class SchedulerZmqConfigs:  # pragma: no cover
    def __init__(self, *_args, **_kwargs):
        pass
sched.EngineQueue = EngineQueue  # type: ignore[attr-defined]
sched.SchedulerZmqConfigs = SchedulerZmqConfigs  # type: ignore[attr-defined]

# max.serve.telemetry.metrics
metrics = _ensure_module("max.serve.telemetry.metrics")
class _Metrics:  # pragma: no cover
    def configure(self, **_kwargs):
        return None
    def input_time(self, *_args):
        return None
    def output_time(self, *_args):
        return None
    def ttft(self, *_args):
        return None
    def itl(self, *_args):
        return None
metrics.METRICS = _Metrics()  # type: ignore[attr-defined]

# max.serve.telemetry.stopwatch
sw = _ensure_module("max.serve.telemetry.stopwatch")
class StopWatch:  # pragma: no cover
    @property
    def elapsed_ms(self) -> float:
        return 0.0
    def reset(self) -> None:
        return None
def record_ms(_metric):  # pragma: no cover
    from contextlib import contextmanager
    @contextmanager
    def _cm():
        yield None
    return _cm()
sw.StopWatch = StopWatch  # type: ignore[attr-defined]
sw.record_ms = record_ms  # type: ignore[attr-defined]

# max.dtype
mdtype = _ensure_module("max.dtype")
class DType:  # pragma: no cover
    pass
mdtype.DType = DType  # type: ignore[attr-defined]

# max.graph
mgraph = _ensure_module("max.graph")
class DeviceRef:  # pragma: no cover
    pass
mgraph.DeviceRef = DeviceRef  # type: ignore[attr-defined]
mgraph_weights = _ensure_module("max.graph.weights")
class WeightsAdapter:  # pragma: no cover
    pass
class WeightsFormat:  # pragma: no cover
    pass
mgraph_weights.WeightsAdapter = WeightsAdapter  # type: ignore[attr-defined]
mgraph_weights.WeightsFormat = WeightsFormat  # type: ignore[attr-defined]

# max.engine.api
mengine = _ensure_module("max.engine")
mengine_api = _ensure_module("max.engine.api")
class InferenceSession:  # pragma: no cover
    pass
mengine_api.InferenceSession = InferenceSession  # type: ignore[attr-defined]
mengine.api = mengine_api  # type: ignore[attr-defined]

# max.serve.pipelines.model_worker
mw = _ensure_module("max.serve.pipelines.model_worker")
class _CM:  # pragma: no cover - async CM
    async def __aenter__(self):
        return SimpleNamespace()
    async def __aexit__(self, exc_type, exc, tb):
        return False
def start_model_worker(*_args, **_kwargs):
    return _CM()
mw.start_model_worker = start_model_worker  # type: ignore[attr-defined]

# max.serve.pipelines.telemetry_worker
tw = _ensure_module("max.serve.pipelines.telemetry_worker")
def start_telemetry_consumer(*_args, **_kwargs):
    return _CM()
tw.start_telemetry_consumer = start_telemetry_consumer  # type: ignore[attr-defined]

# sse_starlette.sse minimal stub (if missing)
sse = _ensure_module("sse_starlette.sse")
class EventSourceResponse:  # pragma: no cover
    def __init__(self, *_args, **_kwargs):
        pass
sse.EventSourceResponse = EventSourceResponse  # type: ignore[attr-defined]


@pytest.fixture(scope="session")
def openai_app():
    from importlib import import_module
    try:
        openai_local = import_module("quote.server.openai.local")
    except Exception:
        pytest.skip("quote.server.openai.local not available in this environment")

    @asynccontextmanager
    async def fake_lifespan(app, tokenizer, model_id: str):
        class StubPipeline:
            def __init__(self, model_name: str, tokenizer: object):
                self.model_name = model_name
                self.tokenizer = tokenizer

            async def __aenter__(self):  # pragma: no cover - minimal impl
                return self

            async def __aexit__(self, exc_type, exc, tb):  # pragma: no cover
                return False

            async def next_token(self, request):
                # Emit a very short, deterministic response per request
                text = "ok"
                for ch in text:
                    yield SimpleNamespace(
                        decoded_token=ch,
                        removed_n=None,
                        status=SimpleNamespace(is_done=False),
                    )
                # Signal completion
                yield SimpleNamespace(
                    decoded_token=None,
                    removed_n=None,
                    status=SimpleNamespace(is_done=True),
                )

        # Install stub pipeline
        app.state.pipeline = StubPipeline(model_id, tokenizer)
        try:
            yield
        finally:
            pass

    # Patch lifespan to avoid starting real workers
    try:
        setattr(openai_local, "lifespan", fake_lifespan)
    except Exception:
        pass

    # Build the app using the patched lifespan
    app = openai_local.create_app()
    return app


@pytest.fixture(scope="session")
def openai_client(openai_app):
    from fastapi.testclient import TestClient
    with TestClient(openai_app) as client:
        yield client
