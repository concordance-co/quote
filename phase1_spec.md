# Phase 1 Spec: Feature-Triggered Mods + Jailbreak Adaptive Environment

## Depends On

Phase 0 complete: HuggingFace backend running, hidden states + attention patterns accessible inline, existing mods working.

## Goal

1. Connect SAE feature extraction to the generation loop (the bridge between observer and mod system)
2. Build the feature-triggered mod primitive — mods that fire based on activation patterns, not just token events
3. Build a jailbreak adaptive environment as the first domain — eval harness + prompting ceiling + feature-based detection
4. Multi-signal: use hidden states (SAE features) + attention patterns together
5. Ship externally: demo, blog post, open-source the pattern

**Timeline:** ~3-4 weeks after Phase 0

---

## Architecture Overview

```
Generation Loop (Phase 0)
    │
    ├── ForwardPass event (with hidden_states + attention_patterns)
    │         │
    │         ▼
    │   ┌─────────────────────┐
    │   │  Feature Extractor  │  ← SAE encodes hidden states → top-k feature activations
    │   │  (inline, async)    │  ← Attention analyzer extracts pattern metrics
    │   └─────────────────────┘
    │         │
    │         ▼
    │   ┌─────────────────────┐
    │   │  Feature-Triggered  │  ← "if feature X > threshold, do action Y"
    │   │  Mod Dispatch       │  ← "if attention entropy drops below Z, flag"
    │   └─────────────────────┘
    │         │
    │         ▼
    │   ModAction (ForceTokens, AdjustedLogits, EmitError, etc.)
    │
    ▼
Next token
```

The key insight: feature extraction becomes a **step in the event pipeline**, not a separate sidecar. The ForwardPass event arrives with hidden states, the feature extractor processes them, and feature-triggered mods react — all within the same generation step, with ~1 token of async latency.

---

## Module 1: Inline Feature Extractor

**Purpose:** Encode hidden states through an SAE to produce feature activations during generation. Replaces the post-hoc SAE sidecar.

### Location
```
engine/inference/src/quote/
├── features/
│   ├── __init__.py
│   ├── extractor.py              # SAE feature extraction from hidden states
│   ├── attention_analyzer.py     # Attention pattern metrics
│   ├── signals.py                # Combined multi-signal output type
│   └── sae_loader.py             # SAE model loading (port from existing sae_loader.py)
```

### `extractor.py` — SAE Feature Extraction

**Inputs:**
- `hidden_states: Tensor` — shape `(hidden_dim,)` from ForwardPass event (or `(seq_len, hidden_dim)` from Prefilled)
- `sae_model` — loaded SAE from sae-lens

**Outputs:**
```python
@dataclass
class FeatureActivations:
    top_k_indices: list[int]          # feature IDs of top-k activated features
    top_k_values: list[float]         # activation values for top-k features
    all_activations: Tensor | None    # full activation vector (optional, for data pipeline)
    layer: int
    position: int                     # token position in sequence
```

**Implementation:**
- Port the core logic from existing `engine/inference/src/quote/interpretability/feature_extractor.py`
- Load SAE via sae-lens: `SAE.from_pretrained()` with LlamaScope 8x release
- Encode: `sae.encode(hidden_states)` → sparse activation vector (32K features)
- Extract top-k: sort by activation value, return top 20 (configurable)
- Filter zero activations (existing behavior from `sae_loader.py:137`)

**Key difference from current sidecar:**
- NO separate HuggingFace forward pass — hidden states come from the generation loop directly
- NO numerical mismatch between inference engine and SAE analysis
- Runs on same device as the model (MPS/CUDA/CPU)

**SAE loading:**
- `sae_id`: default `"EleutherAI/sae-llama-3.1-8b-32x"` (but using 8x for Neuronpedia descriptions)
- Configurable `sae_id`, `layer`, `top_k` via `FeatureConfig`
- SAE loads once at startup, stays in memory
- If SAE loading fails, feature extraction degrades gracefully (returns empty activations, doesn't crash generation)

### `attention_analyzer.py` — Attention Pattern Metrics

**Inputs:**
- `attention_patterns: Tensor` — shape `(num_heads, 1, seq_len)` from ForwardPass event

**Outputs:**
```python
@dataclass
class AttentionMetrics:
    entropy_per_head: list[float]         # attention entropy per head (high = diffuse, low = focused)
    max_attention_per_head: list[float]   # max attention weight per head
    max_attention_position: list[int]     # which position each head attends to most
    attention_to_injection: float | None  # avg attention weight to injected token positions (if known)
    layer: int
    position: int
```

**Implementation:**
- Entropy: `-sum(p * log(p))` per head across the key dimension
- Max attention: `max(attention_weights)` per head
- Attention to injection: if injected token positions are known (from mod system), compute average attention to those positions across heads
- These are cheap to compute — just numpy ops on the attention tensor

**Why these metrics:**
- Entropy drop = model suddenly focuses on something (potential jailbreak trigger)
- Attention to injected tokens = direct measure of how much the injection is influencing generation
- Per-head breakdown = different heads attend to different things; some may be more sensitive to adversarial inputs

### `signals.py` — Combined Multi-Signal Output

```python
@dataclass
class InferenceSignals:
    features: FeatureActivations | None
    attention: AttentionMetrics | None
    position: int
    token_id: int | None
    timestamp: float
```

This is the unified type that feature-triggered mods receive. It bundles all available signals for a given generation step.

### Config

```python
@dataclass
class FeatureConfig:
    enabled: bool = True
    sae_id: str = "EleutherAI/sae-llama-3.1-8b-32x"  # 8x expansion, 32K features
    layer: int = 16
    top_k: int = 20
    store_full_activations: bool = False   # for data pipeline (Phase 3)

@dataclass
class AttentionConfig:
    enabled: bool = True
    layer: int = 16                        # same layer as SAE by default
    compute_entropy: bool = True
    track_injection_attention: bool = True  # requires knowing injected positions

@dataclass
class SignalConfig:
    features: FeatureConfig = field(default_factory=FeatureConfig)
    attention: AttentionConfig = field(default_factory=AttentionConfig)
```

---

## Module 2: Feature-Triggered Mod Primitive

**Purpose:** A new mod type that triggers based on feature activations and attention metrics, not just token events.

### Location
```
engine/sdk/quote_mod_sdk/
├── feature_mod.py                # NEW — @feature_mod decorator + FeatureEvent
```

### `feature_mod.py`

**New event type** (added to `shared/types.py`):
```python
class FeatureEvent(ModEvent):
    """Emitted after feature extraction, before sampling."""
    request_id: str
    step: int
    signals: InferenceSignals           # combined features + attention metrics
    input_ids: list[int]                # full sequence so far
    logits: Tensor                      # current logits (can be modified)
```

**New decorator:**
```python
@feature_mod(
    trigger=FeatureTrigger(
        feature_ids=[4721, 8832],       # fire if ANY of these features activate
        threshold=0.5,                   # minimum activation value
        attention_entropy_below=2.0,     # OR if attention entropy drops below this
    )
)
def jailbreak_detector(event: FeatureEvent, actions: ActionBuilder, tokenizer) -> ModAction:
    # This function only runs if the trigger condition is met
    # Access: event.signals.features, event.signals.attention
    return actions.emit_error("Jailbreak detected via feature activation")
```

**Trigger types:**
```python
@dataclass
class FeatureTrigger:
    # Feature-based triggers (OR logic within, AND logic between categories)
    feature_ids: list[int] | None = None          # fire if any of these activate
    threshold: float = 0.0                         # minimum activation value
    feature_absent: list[int] | None = None        # fire if these features are NOT active

    # Attention-based triggers
    attention_entropy_below: float | None = None   # fire if entropy drops below
    attention_entropy_above: float | None = None   # fire if entropy spikes above
    attention_to_injection_above: float | None = None  # fire if attention to injected tokens exceeds

    # Compound: all specified conditions must be true (AND logic)
    require_all: bool = False                      # if True, ALL conditions must match; if False, ANY
```

**Dispatch integration:**
- `FeatureEvent` is emitted AFTER `ForwardPass` event and BEFORE sampling
- Insert into the generation loop in `generation.py`:
  1. ForwardPass event → dispatch to regular mods
  2. Extract features from hidden states + compute attention metrics
  3. Emit FeatureEvent → dispatch to feature mods (only those whose triggers match)
  4. Process any actions from feature mods
  5. Sample token
- Feature mods can return the same actions as ForwardPass mods: `AdjustedLogits`, `ForceTokens`, `Backtrack`, terminals

**Validation rules for FeatureEvent:**
Same as ForwardPass: `Noop`, `ForceTokens`, `Backtrack`, `ForceOutput`, `ToolCalls`, `AdjustedLogits`, `EmitError`

### Why a new event type (not just enriching ForwardPass)?

- Separation of concerns: regular mods don't need to know about features
- Trigger filtering: feature mods only run when their trigger conditions match, saving compute
- Ordering: features are extracted AFTER regular ForwardPass mods run (so AdjustedLogits from regular mods are applied first)
- Backward compatibility: existing mods never see FeatureEvent

---

## Module 3: Jailbreak Adaptive Environment

**Purpose:** A complete eval environment for jailbreak detection that establishes the prompting ceiling, trains feature-based detection, and measures the gap. This is the first domain and the template for future domains.

### Location
```
engine/environments/
├── __init__.py
├── base.py                       # Base environment class
├── jailbreak/
│   ├── __init__.py
│   ├── environment.py            # Jailbreak eval environment
│   ├── dataset.py                # Jailbreak prompt dataset (curated + generated)
│   ├── prompting_baseline.py     # System prompt detection baseline
│   ├── feature_detector.py       # Feature-based jailbreak detector (feature_mod)
│   ├── eval_harness.py           # Runs both detectors, compares, reports
│   └── adaptive.py               # Adaptive prompt generation (probes the detector)
```

### `base.py` — Environment Base Class

```python
class Environment:
    """Base class for eval environments. Each domain (jailbreak, SWE safety, etc.) implements one."""

    def get_dataset(self) -> list[EvalCase]: ...
    def get_prompting_baseline(self) -> Detector: ...
    def get_feature_detector(self) -> Detector: ...
    def run_eval(self, backend: Backend, config: GenerationConfig) -> EvalReport: ...
    def run_adaptive(self, backend: Backend, rounds: int) -> AdaptiveReport: ...

@dataclass
class EvalCase:
    prompt: str
    is_jailbreak: bool                    # ground truth label
    category: str                         # attack type: "DAN", "roleplay", "encoding", "benign", etc.
    difficulty: str                       # "easy", "medium", "hard"
    source: str                           # where this case came from

@dataclass  
class DetectionResult:
    detected: bool
    confidence: float
    method: str                           # "prompting" or "feature" or "multi-signal"
    latency_ms: float
    signals_used: dict                    # which features/attention metrics triggered
    
@dataclass
class EvalReport:
    prompting_results: list[DetectionResult]
    feature_results: list[DetectionResult]
    prompting_accuracy: float
    feature_accuracy: float
    prompting_precision: float
    feature_precision: float
    prompting_recall: float
    feature_recall: float
    gap_analysis: dict                    # where features beat prompting and vice versa
    latency_comparison: dict              # avg latency for each method
```

### `dataset.py` — Jailbreak Prompt Dataset

**Initial dataset (curated, ~200-500 cases):**
- Known jailbreak techniques: DAN prompts, roleplay attacks, encoding attacks (base64, ROT13), prefix injection, context manipulation
- Benign prompts that look suspicious but aren't (to test false positive rate)
- Sources: existing jailbreak benchmarks (JailbreakBench, HarmBench), manual curation
- Each case labeled with ground truth, attack category, difficulty

**Format:**
```python
@dataclass
class JailbreakCase(EvalCase):
    attack_technique: str                 # "DAN", "roleplay", "base64", "prefix_injection", etc.
    expected_features: list[int] | None   # if known, which SAE features should activate
```

**Dataset loading:** JSON file, checked into repo, easily extensible.

### `prompting_baseline.py` — Prompting Ceiling

**Purpose:** Best-effort jailbreak detection using ONLY prompting (no model internals). This is the ceiling we need to beat or complement.

**Approaches to implement:**
1. **System prompt classifier:** Ask the model "Is this a jailbreak attempt? Yes/No" with a carefully crafted system prompt
2. **Few-shot classification:** Include examples of jailbreaks and benign prompts in the system prompt
3. **Output monitoring:** Let the model respond, then check if the response indicates compliance with a harmful request

**Each approach returns:**
- `detected: bool`
- `confidence: float` (from logprobs if available, or parsed from model output)
- `latency_ms: float`

**The prompting baseline must be genuinely strong.** Don't strawman it. Use the best techniques available. The whole point is showing where features add something prompting can't.

### `feature_detector.py` — Feature-Based Jailbreak Detector

**Purpose:** Detect jailbreaks using SAE features + attention patterns. This is a `@feature_mod`.

**Approach:**

Phase A — Feature discovery (run once, produces a feature set):
1. Run the jailbreak dataset through the model with feature extraction enabled
2. For each prompt, record top-k SAE features at every position
3. Compare feature distributions: jailbreak prompts vs. benign prompts
4. Identify features that are significantly more active in jailbreaks (statistical test: difference in mean activation, Welch's t-test or similar)
5. Output: a list of "jailbreak-associated features" with thresholds

Phase B — Detector (runs at inference time as a feature_mod):
```python
@feature_mod(
    trigger=FeatureTrigger(
        feature_ids=JAILBREAK_FEATURES,     # from Phase A discovery
        threshold=JAILBREAK_THRESHOLD,       # from Phase A calibration
    )
)
def jailbreak_feature_detector(event, actions, tokenizer):
    signals = event.signals

    # Feature signal
    feature_score = compute_feature_score(signals.features, JAILBREAK_FEATURES)

    # Attention signal
    attention_score = 0.0
    if signals.attention:
        # Low entropy = model suddenly focused = potential trigger
        avg_entropy = mean(signals.attention.entropy_per_head)
        attention_score = max(0, ENTROPY_BASELINE - avg_entropy)

    # Combined score
    combined_score = FEATURE_WEIGHT * feature_score + ATTENTION_WEIGHT * attention_score

    if combined_score > DETECTION_THRESHOLD:
        return actions.emit_error(f"Jailbreak detected (score: {combined_score:.2f})")
    return actions.noop()
```

**Multi-signal approach:**
- Feature activation score: weighted sum of jailbreak-associated feature activations
- Attention entropy: drop in entropy indicates unusual focus
- Attention to injection: high attention to injected/suspicious tokens
- Combine with learned or hand-tuned weights initially

### `eval_harness.py` — Evaluation Runner

**Purpose:** Run both detectors on the dataset, produce comparable results.

```python
def run_eval(environment, backend, config) -> EvalReport:
    dataset = environment.get_dataset()
    prompting_detector = environment.get_prompting_baseline()
    feature_detector = environment.get_feature_detector()

    prompting_results = []
    feature_results = []

    for case in dataset:
        # Run prompting baseline
        p_result = prompting_detector.detect(case.prompt, backend, config)
        prompting_results.append(p_result)

        # Run feature-based detector
        f_result = feature_detector.detect(case.prompt, backend, config)
        feature_results.append(f_result)

    return EvalReport(
        prompting_results=prompting_results,
        feature_results=feature_results,
        # Compute accuracy, precision, recall, F1 for both
        # Gap analysis: which cases does features catch that prompting misses?
        # Latency comparison
    )
```

**Key outputs:**
- Accuracy/precision/recall/F1 for both methods
- **Gap analysis:** Cases where features catch what prompting misses (and vice versa)
- **Latency comparison:** Feature detection should be faster (no extra model call)
- **Robustness comparison:** Run adversarial rephrasing of jailbreaks — which method degrades less?
- **Per-category breakdown:** Which attack types does each method handle best?

### `adaptive.py` — Adaptive Probing

**Purpose:** Automatically generate new jailbreak variants that probe the detector's weaknesses. This is how the environment improves itself and how the dataset grows.

```python
def run_adaptive(environment, backend, rounds=10) -> AdaptiveReport:
    detector = environment.get_feature_detector()
    dataset = environment.get_dataset()

    for round in range(rounds):
        # 1. Find cases the detector currently misses
        missed = [case for case in dataset if not detector.detect(case.prompt, backend)]

        # 2. Generate variants of successful detections that might evade
        # Use the model itself (or a separate model) to rephrase jailbreaks
        variants = generate_adversarial_variants(dataset, backend)

        # 3. Test variants against detector
        evasions = [v for v in variants if not detector.detect(v.prompt, backend)]

        # 4. Add successful evasions to dataset (with labels)
        dataset.extend(evasions)

        # 5. Re-run feature discovery on expanded dataset
        # Update jailbreak-associated features + thresholds
        detector.update_features(dataset, backend)

    return AdaptiveReport(
        initial_accuracy=...,
        final_accuracy=...,
        rounds=rounds,
        evasions_found=len(all_evasions),
        dataset_growth=len(dataset) - initial_size,
        feature_drift=...  # how much the feature set changed
    )
```

**Why adaptive matters:**
- Static detectors are brittle. The adaptive loop tests robustness automatically.
- Each round produces new labeled data → feeds the data pipeline.
- Feature drift (which features matter changes as attacks evolve) is itself a signal.
- This is the "environment" from the roadmap thesis — not just a dataset, an evolving eval system.

---

## Module 4: Activation Logging (Data Pipeline Foundation)

**Purpose:** Log feature activations + attention metrics for every generation step. This is the foundation of the data pipeline from the roadmap.

### Location
```
engine/inference/src/quote/
├── data/
│   ├── __init__.py
│   ├── activation_logger.py      # Structured logging of signals per step
│   └── schemas.py                # Data schemas for activation logs
```

### `activation_logger.py`

```python
class ActivationLogger:
    """Logs feature activations and attention metrics per generation step."""

    def __init__(self, output_dir: str, format: str = "jsonl"):
        ...

    def log_step(self, request_id: str, step: int, signals: InferenceSignals,
                 token_id: int, mod_actions: list[ModAction]):
        """Log one generation step's signals + actions taken."""
        ...

    def log_request(self, request_id: str, prompt: str, output: str,
                    metadata: dict):
        """Log request-level metadata."""
        ...

    def flush(self):
        """Write buffered logs to disk."""
        ...
```

**Log schema (per step):**
```json
{
    "request_id": "...",
    "step": 0,
    "token_id": 1234,
    "features": {
        "top_k_indices": [4721, 8832, ...],
        "top_k_values": [0.92, 0.85, ...],
        "layer": 16
    },
    "attention": {
        "entropy_per_head": [3.2, 2.8, ...],
        "max_attention_position": [0, 15, ...],
        "attention_to_injection": 0.45
    },
    "mod_actions": ["Noop", "ForceTokens"],
    "timestamp": 1700000000.0
}
```

**This is intentionally simple (JSONL) for now.** Parquet/database storage comes in Phase 3 when volume demands it. The schema is what matters — it must be consistent from day 1 so data is comparable across runs.

### Integration with Generation Loop

In `generation.py`, after feature extraction and mod dispatch:
```python
if activation_logger:
    activation_logger.log_step(request_id, step, signals, token_id, actions)
```

Optional — controlled by config. Off by default for interactive use, on for eval harness runs.

---

## Generation Loop Update (changes to Phase 0's `generation.py`)

The Phase 0 generation loop gets a new step between ForwardPass dispatch and sampling:

```python
# Phase 0 flow:
# ForwardPass → dispatch mods → sample → Sampled → dispatch mods → Added → dispatch mods

# Phase 1 flow:
# ForwardPass → dispatch regular mods
#     → extract features (SAE encode hidden states)
#     → compute attention metrics
#     → emit FeatureEvent → dispatch feature_mods (only matching triggers)
#     → log signals (if logger enabled)
#     → sample → Sampled → dispatch mods → Added → dispatch mods
```

The feature extraction + dispatch adds ~5-50ms per step depending on SAE complexity and number of feature mods. This is acceptable for the use case.

---

## Deliverables (Definition of Done)

### Feature Extraction
- [ ] SAE loads from sae-lens, encodes hidden states inline during generation
- [ ] No separate HuggingFace forward pass — uses hidden states from the generation loop directly
- [ ] Top-k feature activations available per token position
- [ ] Attention metrics (entropy, max attention, injection attention) computed per step
- [ ] `InferenceSignals` bundles features + attention into single type
- [ ] Graceful degradation: if SAE fails to load, generation continues without features

### Feature-Triggered Mods
- [ ] `@feature_mod` decorator with `FeatureTrigger` conditions
- [ ] `FeatureEvent` emitted between ForwardPass and sampling
- [ ] Feature mods only dispatch when trigger conditions match
- [ ] Feature mods can return same actions as ForwardPass mods
- [ ] Existing regular mods unaffected by feature mod additions

### Jailbreak Environment
- [ ] Curated dataset of 200+ jailbreak/benign cases with labels and categories
- [ ] Prompting baseline detector with 3 approaches (system prompt, few-shot, output monitoring)
- [ ] Feature-based detector using discovered jailbreak-associated features
- [ ] Multi-signal detector combining features + attention
- [ ] Eval harness that runs both detectors and produces comparable metrics
- [ ] Gap analysis: concrete examples where features catch what prompting misses
- [ ] Adaptive probing: at least 3 rounds of adversarial variant generation

### Data Pipeline Foundation
- [ ] Activation logger producing structured JSONL per generation step
- [ ] Schema covers features, attention metrics, and mod actions
- [ ] Logger integrates with generation loop and eval harness

### External Shipping
- [ ] Blog post: "Reading a Model's Mind at Inference Time" (or similar)
- [ ] Demo video showing feature-triggered jailbreak detection
- [ ] Open-source: feature_mod pattern, jailbreak environment, eval harness
- [ ] Published results: prompting vs. features accuracy/latency/robustness comparison

---

## NOT in Scope (Phase 1)

- Training custom SAEs (we use EleutherAI's LlamaScope)
- Causal intervention / activation patching (read-only observation)
- Multi-model feature extraction (Llama-3.1-8B only)
- Production deployment of the jailbreak detector (demo-grade)
- Neuronpedia integration for feature descriptions (nice-to-have, not blocking)
- Multi-layer feature extraction (single configured layer for now)
- Parquet/database storage for activation data (JSONL is fine for now)
- vLLM backend (still HuggingFace only)

## Open Questions

- [ ] Which SAE variant gives best jailbreak feature separation? 8x (32K) vs 32x (128K) — 32x lacks Neuronpedia descriptions but might separate better
- [ ] Is layer 16 optimal for jailbreak detection, or should we sweep layers during feature discovery?
- [ ] How much does attention entropy actually correlate with jailbreak attempts? Feature discovery will answer this empirically.
- [ ] Should the adaptive environment use the same model for variant generation, or a separate model (to avoid contamination)?

## Key Risk

**Features don't separate jailbreaks cleanly at layer 16 with 8x SAEs.**

Mitigation: This is why the eval harness exists. If single-layer SAE features alone don't separate well enough:
1. Try other layers (configurable)
2. Multi-signal (features + attention) may work where features alone don't
3. Simple linear probes on raw hidden states as a fallback
4. The environment and eval harness are still valuable even if the first detector is mediocre — they're the template for every future domain

Finding "features don't work well for jailbreaks" in 3-4 weeks is a cheap, useful finding. Going dark for 3 months hoping they do is not.
