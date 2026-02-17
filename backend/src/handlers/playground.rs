//! Playground handlers for the playable mod interface.
//!
//! This module provides HTTP handlers for:
//! - Generating temporary API keys for playground users
//! - Generating Python mod code from user-specified parameters
//! - Uploading mods to model servers
//! - Running inference with mods

use axum::{http::{StatusCode, HeaderMap}, extract::State, Json};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, VecDeque};
use std::env;
use std::sync::{Mutex, OnceLock};
use std::time::Instant;

use crate::utils::{AppState, auth::{generate_api_key, extract_api_key_from_headers}};

/// Rate limiter for the analyze_features endpoint.
/// Tracks per-API-key request timestamps in a sliding window.
static ANALYZE_RATE_LIMITER: OnceLock<Mutex<HashMap<String, VecDeque<Instant>>>> = OnceLock::new();

const RATE_LIMIT_MAX_REQUESTS: usize = 5;
const RATE_LIMIT_WINDOW_SECS: u64 = 60;

fn check_rate_limit(api_key: &str) -> Result<(), ()> {
    let limiter = ANALYZE_RATE_LIMITER.get_or_init(|| Mutex::new(HashMap::new()));
    let mut map = limiter.lock().unwrap_or_else(|e| e.into_inner());
    let timestamps = map.entry(api_key.to_string()).or_default();

    let now = Instant::now();
    let window = std::time::Duration::from_secs(RATE_LIMIT_WINDOW_SECS);

    // Remove expired timestamps
    while let Some(front) = timestamps.front() {
        if now.duration_since(*front) > window {
            timestamps.pop_front();
        } else {
            break;
        }
    }

    if timestamps.len() >= RATE_LIMIT_MAX_REQUESTS {
        return Err(());
    }

    timestamps.push_back(now);
    Ok(())
}

/// Model endpoints configuration
#[derive(Debug, Clone)]
pub struct ModelEndpoints {
    pub qwen_14b: String,
    pub llama_8b: String,
    pub sae: String,
}

impl ModelEndpoints {
    pub fn from_env() -> Self {
        Self {
            qwen_14b: env::var("PLAYGROUND_QWEN_14B_URL").unwrap_or_default(),
            llama_8b: env::var("PLAYGROUND_LLAMA_8B_URL").unwrap_or_default(),
            sae: env::var("PLAYGROUND_SAE_URL").unwrap_or_default(),
        }
    }

    pub fn get_url(&self, model: &str) -> Option<&str> {
        let url = match model {
            "qwen-14b" => &self.qwen_14b,
            "llama-3.1-8b" => &self.llama_8b,
            _ => return None,
        };
        if url.is_empty() { None } else { Some(url) }
    }

    pub fn get_sae_url(&self) -> Option<&str> {
        if self.sae.is_empty() { None } else { Some(&self.sae) }
    }

    pub fn get_model_id(&self, model: &str) -> Option<&str> {
        match model {
            "qwen-14b" => Some("Qwen/Qwen3-14B-GGUF"),
            "llama-3.1-8b" => Some("modularai/Llama-3.1-8B-Instruct-GGUF"),
            _ => None,
        }
    }
}

fn model_endpoint_env_var(model: &str) -> Option<&'static str> {
    match model {
        "qwen-14b" => Some("PLAYGROUND_QWEN_14B_URL"),
        "llama-3.1-8b" => Some("PLAYGROUND_LLAMA_8B_URL"),
        _ => None,
    }
}

fn resolve_model_endpoint<'a>(
    endpoints: &'a ModelEndpoints,
    model: &str,
) -> Result<&'a str, (StatusCode, Json<serde_json::Value>)> {
    if let Some(endpoint) = endpoints.get_url(model) {
        return Ok(endpoint);
    }

    if let Some(env_var) = model_endpoint_env_var(model) {
        return Err((
            StatusCode::SERVICE_UNAVAILABLE,
            Json(serde_json::json!({
                "error": format!("Model endpoint not configured for {}. Missing/empty {}.", model, env_var),
                "code": 503
            })),
        ));
    }

    Err((
        StatusCode::BAD_REQUEST,
        Json(serde_json::json!({
            "error": format!("Unknown model: {}", model),
            "code": 400
        })),
    ))
}

/// Available injection positions
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum InjectionPosition {
    /// Inject at the start of generation
    Start,
    /// Inject after N tokens
    AfterTokens,
    /// Inject after N sentences (period detection)
    AfterSentences,
    /// Backtrack and replace at end of turn (EOT detection)
    EotBacktrack,
    /// Detect a phrase and replace it (backtrack + force)
    PhraseReplace,
    /// Inject at the start of reasoning (after <think> opens)
    ReasoningStart,
    /// Inject after N tokens within the <think> block
    ReasoningMid,
    /// Inject before </think> closes (backtrack and insert)
    ReasoningEnd,
    /// Inject at the start of response (after </think>)
    ResponseStart,
    /// Inject after N tokens in the response portion
    ResponseMid,
    /// Inject before EOS in the response (post-reasoning EotBacktrack)
    ResponseEnd,
    /// Detect and replace a phrase within the <think> block
    ReasoningPhraseReplace,
    /// Detect and replace a phrase in the response (after </think>)
    ResponsePhraseReplace,
    /// Detect and replace a phrase across the entire stream (reasoning + response)
    FullStreamPhraseReplace,
}

/// Request body for generating a playground API key
#[derive(Debug, Deserialize)]
pub struct GeneratePlaygroundKeyRequest {
    /// Optional session identifier for tracking
    pub session_id: Option<String>,
}

/// Response for generating a playground API key
#[derive(Debug, Serialize)]
pub struct GeneratePlaygroundKeyResponse {
    /// The API key to use for playground operations
    pub api_key: String,
    /// Message about the key
    pub message: String,
}

/// Generate a temporary API key for playground users
///
/// POST /playground/api-key
///
/// This creates a new API key locally. Registration with model servers
/// happens lazily when the user uploads a mod or runs inference.
pub async fn generate_playground_key(
    State(state): State<AppState>,
    Json(request): Json<GeneratePlaygroundKeyRequest>,
) -> Result<Json<GeneratePlaygroundKeyResponse>, (StatusCode, Json<serde_json::Value>)> {
    // Generate a new API key
    let (full_key, key_hash, key_prefix) = generate_api_key();

    // Store in our database for tracking (optional, with allowed_api_key set to itself)
    let session_name = request
        .session_id
        .unwrap_or_else(|| format!("playground_{}", &key_prefix));

    let _ = sqlx::query(
        r#"
        INSERT INTO api_keys (key_hash, key_prefix, name, description, allowed_api_key, is_admin)
        VALUES ($1, $2, $3, $4, $5, FALSE)
        "#,
    )
    .bind(&key_hash)
    .bind(&key_prefix)
    .bind(&session_name)
    .bind("Playground session key")
    .bind(&full_key) // allowed_api_key = the key itself (can only see own data)
    .execute(&state.db_pool)
    .await;
    // Ignore errors - key generation still succeeds

    Ok(Json(GeneratePlaygroundKeyResponse {
        api_key: full_key,
        message: "API key generated".to_string(),
    }))
}

/// Register an API key with a specific model server
async fn register_key_with_server(
    client: &reqwest::Client,
    endpoint: &str,
    api_key: &str,
    admin_key: &str,
) -> Result<(), (StatusCode, Json<serde_json::Value>)> {
    let add_user_url = format!("{}/add_user", endpoint);
    tracing::info!("Registering API key with model server: {}", add_user_url);
    
    let response = client
        .post(&add_user_url)
        .json(&serde_json::json!({
            "user_api_key": api_key,
            "admin_key": admin_key
        }))
        .send()
        .await
        .map_err(|e| {
            tracing::error!("Failed to register key with {}: {}", endpoint, e);
            (
                StatusCode::BAD_GATEWAY,
                Json(serde_json::json!({
                    "error": format!("Failed to register key with model server ({}): {}", endpoint, e),
                    "code": 502
                })),
            )
        })?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err((
            StatusCode::BAD_GATEWAY,
            Json(serde_json::json!({
                "error": format!("Model server rejected key registration: {} - {}", status, body),
                "code": 502
            })),
        ));
    }
    
    Ok(())
}

/// Mod configuration from the user
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModConfig {
    /// The string to inject
    pub injection_string: String,
    /// Where to inject
    pub position: InjectionPosition,
    /// Number of tokens (for AfterTokens position)
    pub token_count: Option<u32>,
    /// Number of sentences (for AfterSentences position)
    pub sentence_count: Option<u32>,
    /// Phrases to detect and replace (for PhraseReplace positions) - supports multiple for capitalization variants
    pub detect_phrases: Option<Vec<String>>,
    /// Replacements for the detected phrases (for PhraseReplace positions) - parallel array to detect_phrases
    pub replacement_phrases: Option<Vec<String>>,
}

/// Request body for generating mod code
#[derive(Debug, Deserialize)]
pub struct GenerateModRequest {
    /// Mod configuration
    pub config: ModConfig,
}

/// Response for generating mod code
#[derive(Debug, Serialize)]
pub struct GenerateModResponse {
    /// The generated Python mod code
    pub code: String,
    /// The mod name (function name)
    pub mod_name: String,
}

/// Generate Python mod code from configuration
///
/// POST /playground/mods/generate
pub async fn generate_mod_code(
    Json(request): Json<GenerateModRequest>,
) -> Result<Json<GenerateModResponse>, (StatusCode, Json<serde_json::Value>)> {
    let config = &request.config;
    
    // Validate configuration
    match config.position {
        InjectionPosition::AfterTokens | InjectionPosition::ReasoningMid | InjectionPosition::ResponseMid => {
            if config.token_count.is_none() || config.token_count == Some(0) {
                return Err((
                    StatusCode::BAD_REQUEST,
                    Json(serde_json::json!({
                        "error": "token_count is required for this position",
                        "code": 400
                    })),
                ));
            }
        }
        InjectionPosition::AfterSentences => {
            if config.sentence_count.is_none() || config.sentence_count == Some(0) {
                return Err((
                    StatusCode::BAD_REQUEST,
                    Json(serde_json::json!({
                        "error": "sentence_count is required for AfterSentences position",
                        "code": 400
                    })),
                ));
            }
        }
        InjectionPosition::PhraseReplace | InjectionPosition::ReasoningPhraseReplace | InjectionPosition::ResponsePhraseReplace | InjectionPosition::FullStreamPhraseReplace => {
            let has_valid_phrase = config.detect_phrases.as_ref()
                .map(|phrases| phrases.iter().any(|s| !s.is_empty()))
                .unwrap_or(false);
            if !has_valid_phrase {
                return Err((
                    StatusCode::BAD_REQUEST,
                    Json(serde_json::json!({
                        "error": "At least one detect_phrase is required for phrase replace positions",
                        "code": 400
                    })),
                ));
            }
        }
        _ => {}
    }

    let mod_name = "playground_mod";
    let code = generate_mod_python_code(config, mod_name);

    Ok(Json(GenerateModResponse {
        code,
        mod_name: mod_name.to_string(),
    }))
}

/// Build a Python list literal of phrase pairs for phrase replace mods
fn build_phrase_pairs(config: &ModConfig, default_replacement: &str) -> String {
    let detect_phrases = config.detect_phrases.as_ref().map(|v| v.as_slice()).unwrap_or(&[]);
    let replacement_phrases = config.replacement_phrases.as_ref().map(|v| v.as_slice()).unwrap_or(&[]);

    let pairs: Vec<String> = detect_phrases
        .iter()
        .enumerate()
        .filter(|(_, detect)| !detect.is_empty())
        .map(|(i, detect)| {
            let escaped_detect = detect.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n");
            let replacement = replacement_phrases.get(i)
                .filter(|r| !r.is_empty())
                .map(|r| r.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n"))
                .unwrap_or_else(|| escaped_detect.clone());
            format!("(\"{}\", \"{}\")", escaped_detect, replacement)
        })
        .collect();

    if pairs.is_empty() {
        // Fallback to default replacement if no pairs (shouldn't happen due to validation)
        let escaped_default = default_replacement.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n");
        format!("[(\"{}\", \"{}\")]", escaped_default, escaped_default)
    } else {
        format!("[{}]", pairs.join(", "))
    }
}

/// Generate the Python mod code based on configuration
fn generate_mod_python_code(config: &ModConfig, mod_name: &str) -> String {
    let injection_string = config.injection_string.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n");
    
    match config.position {
        InjectionPosition::Start => {
            format!(r#"from quote_mod_sdk import mod, ForwardPass
from dataclasses import dataclass

@dataclass
class State:
    injected: bool = False

states: dict[str, State] = {{}}

@mod
def {mod_name}(event, actions, tokenizer):
    st = states.get(event.request_id)
    if not st:
        states[event.request_id] = State()
        st = states[event.request_id]
    
    if isinstance(event, ForwardPass) and not st.injected:
        st.injected = True
        injection = "{injection_string}"
        tokens = tokenizer.encode(injection, add_special_tokens=False)
        return actions.force_tokens(tokens=tokens)
    
    return actions.noop()
"#, mod_name = mod_name, injection_string = injection_string)
        }
        
        InjectionPosition::AfterTokens => {
            let token_count = config.token_count.unwrap_or(10);
            format!(r#"from quote_mod_sdk import mod, ForwardPass, Added
from dataclasses import dataclass

@dataclass
class State:
    token_count: int = 0
    injected: bool = False

states: dict[str, State] = {{}}

@mod
def {mod_name}(event, actions, tokenizer):
    st = states.get(event.request_id)
    if not st:
        states[event.request_id] = State()
        st = states[event.request_id]
    
    if isinstance(event, ForwardPass) and not st.injected:
        if st.token_count >= {token_count}:
            st.injected = True
            injection = "{injection_string}"
            tokens = tokenizer.encode(injection, add_special_tokens=False)
            return actions.force_tokens(tokens=tokens)
    
    if isinstance(event, Added) and not st.injected:
        st.token_count += len(event.added_tokens)
    
    return actions.noop()
"#, mod_name = mod_name, injection_string = injection_string, token_count = token_count)
        }
        
        InjectionPosition::AfterSentences => {
            let sentence_count = config.sentence_count.unwrap_or(1);
            format!(r#"from quote_mod_sdk import mod, ForwardPass, Added
from dataclasses import dataclass

@dataclass
class State:
    period_count: int = 0
    injected: bool = False

states: dict[str, State] = {{}}

@mod
def {mod_name}(event, actions, tokenizer):
    st = states.get(event.request_id)
    if not st:
        states[event.request_id] = State()
        st = states[event.request_id]
    
    if isinstance(event, ForwardPass) and not st.injected:
        if st.period_count >= {sentence_count}:
            st.injected = True
            injection = "{injection_string}"
            tokens = tokenizer.encode(injection, add_special_tokens=False)
            return actions.force_tokens(tokens=tokens)
    
    if isinstance(event, Added) and not st.injected:
        text = tokenizer.decode(event.added_tokens)
        # Count sentence endings
        for char in text:
            if char in '.!?':
                st.period_count += 1
    
    return actions.noop()
"#, mod_name = mod_name, injection_string = injection_string, sentence_count = sentence_count)
        }
        
        InjectionPosition::EotBacktrack => {
            // For EOT backtrack, we detect the EOS token and backtrack to replace
            format!(r#"from quote_mod_sdk import mod, ForwardPass, Added
from dataclasses import dataclass

@dataclass
class State:
    replaced: bool = False

states: dict[str, State] = {{}}

@mod
def {mod_name}(event, actions, tokenizer):
    st = states.get(event.request_id)
    if not st:
        states[event.request_id] = State()
        st = states[event.request_id]
    
    if isinstance(event, Added) and not st.replaced:
        # Check if this is the EOS token
        if not event.forced:
            text = tokenizer.decode(event.added_tokens)
            # Detect end-of-turn markers
            if any(marker in text for marker in ['<|eot_id|>', '<|end|>', '</s>', '<|im_end|>']):
                st.replaced = True
                # Backtrack and inject our content before the EOS
                injection = "{injection_string}"
                injection_tokens = tokenizer.encode(injection, add_special_tokens=False)
                # Let the model naturally generate EOS after our injection
                return actions.backtrack(
                    steps=len(event.added_tokens),
                    tokens=injection_tokens
                )
    
    return actions.noop()
"#, mod_name = mod_name, injection_string = injection_string)
        }
        
        InjectionPosition::PhraseReplace => {
            let phrase_pairs = build_phrase_pairs(config, &injection_string);

            format!(r#"from quote_mod_sdk import mod, Added
from dataclasses import dataclass

@dataclass
class State:
    accumulated_text: str = ""

states: dict[str, State] = {{}}

# Phrase pairs: (detect, replace)
PHRASE_PAIRS = {phrase_pairs}

@mod
def {mod_name}(event, actions, tokenizer):
    st = states.get(event.request_id)
    if not st:
        states[event.request_id] = State()
        st = states[event.request_id]

    if isinstance(event, Added) and not event.forced:
        text = tokenizer.decode(event.added_tokens)
        st.accumulated_text += text

        # Check each phrase pair
        for needle, replacement in PHRASE_PAIRS:
            if st.accumulated_text.endswith(needle):
                # Remove needle from accumulated text so we can catch future occurrences
                st.accumulated_text = st.accumulated_text[:-len(needle)]
                needle_tokens = tokenizer.encode(needle, add_special_tokens=False)
                replacement_tokens = tokenizer.encode(replacement, add_special_tokens=False)
                return actions.backtrack(
                    steps=len(needle_tokens),
                    tokens=replacement_tokens
                )

    return actions.noop()
"#, mod_name = mod_name, phrase_pairs = phrase_pairs)
        }

        InjectionPosition::ReasoningStart => {
            format!(r#"from quote_mod_sdk import mod, Added
from dataclasses import dataclass

@dataclass
class State:
    accumulated_text: str = ""
    injected: bool = False

states: dict[str, State] = {{}}

@mod
def {mod_name}(event, actions, tokenizer):
    st = states.get(event.request_id)
    if not st:
        states[event.request_id] = State()
        st = states[event.request_id]

    if isinstance(event, Added) and not event.forced and not st.injected:
        text = tokenizer.decode(event.added_tokens)
        st.accumulated_text += text

        if st.accumulated_text.endswith("<think>"):
            st.injected = True
            think_tag = "<think>"
            think_tokens = tokenizer.encode(think_tag, add_special_tokens=False)
            injection = "{injection_string}"
            injection_tokens = tokenizer.encode(injection, add_special_tokens=False)
            return actions.backtrack(
                steps=len(think_tokens),
                tokens=think_tokens + injection_tokens
            )

    return actions.noop()
"#, mod_name = mod_name, injection_string = injection_string)
        }

        InjectionPosition::ReasoningMid => {
            let token_count = config.token_count.unwrap_or(10);
            format!(r#"from quote_mod_sdk import mod, Added
from dataclasses import dataclass

@dataclass
class State:
    accumulated_text: str = ""
    in_reasoning: bool = False
    reasoning_token_count: int = 0
    injected: bool = False

states: dict[str, State] = {{}}

@mod
def {mod_name}(event, actions, tokenizer):
    st = states.get(event.request_id)
    if not st:
        states[event.request_id] = State()
        st = states[event.request_id]

    if isinstance(event, Added) and not event.forced:
        text = tokenizer.decode(event.added_tokens)
        st.accumulated_text += text

        # Detect <think> tag
        if not st.in_reasoning and "<think>" in st.accumulated_text:
            st.in_reasoning = True

        # Detect </think> tag - stop counting
        if st.in_reasoning and "</think>" in st.accumulated_text:
            st.in_reasoning = False

        # Count tokens while in reasoning
        if st.in_reasoning:
            st.reasoning_token_count += len(event.added_tokens)

            if st.reasoning_token_count >= {token_count} and not st.injected:
                st.injected = True
                injection = "{injection_string}"
                tokens = tokenizer.encode(injection, add_special_tokens=False)
                return actions.force_tokens(tokens=tokens)

    return actions.noop()
"#, mod_name = mod_name, injection_string = injection_string, token_count = token_count)
        }

        InjectionPosition::ReasoningEnd => {
            format!(r#"from quote_mod_sdk import mod, Added
from dataclasses import dataclass

@dataclass
class State:
    accumulated_text: str = ""
    injected: bool = False

states: dict[str, State] = {{}}

@mod
def {mod_name}(event, actions, tokenizer):
    st = states.get(event.request_id)
    if not st:
        states[event.request_id] = State()
        st = states[event.request_id]

    if isinstance(event, Added) and not event.forced and not st.injected:
        text = tokenizer.decode(event.added_tokens)
        st.accumulated_text += text

        # Detect </think> tag and inject before it
        if st.accumulated_text.endswith("</think>"):
            st.injected = True
            close_tag = "</think>"
            close_tag_tokens = tokenizer.encode(close_tag, add_special_tokens=False)
            injection = "{injection_string}"
            injection_tokens = tokenizer.encode(injection, add_special_tokens=False)
            # Let the model naturally regenerate </think> after our injection
            return actions.backtrack(
                steps=len(close_tag_tokens),
                tokens=injection_tokens
            )

    return actions.noop()
"#, mod_name = mod_name, injection_string = injection_string)
        }

        InjectionPosition::ResponseStart => {
            format!(r#"from quote_mod_sdk import mod, Added
from dataclasses import dataclass

@dataclass
class State:
    accumulated_text: str = ""
    injected: bool = False

states: dict[str, State] = {{}}

@mod
def {mod_name}(event, actions, tokenizer):
    st = states.get(event.request_id)
    if not st:
        states[event.request_id] = State()
        st = states[event.request_id]

    if isinstance(event, Added) and not event.forced and not st.injected:
        text = tokenizer.decode(event.added_tokens)
        st.accumulated_text += text

        if "</think>" in st.accumulated_text:
            st.injected = True
            injection = "{injection_string}"
            injection_tokens = tokenizer.encode(injection, add_special_tokens=False)
            return actions.force_tokens(tokens=injection_tokens)

    return actions.noop()
"#, mod_name = mod_name, injection_string = injection_string)
        }

        InjectionPosition::ResponseMid => {
            let token_count = config.token_count.unwrap_or(10);
            format!(r#"from quote_mod_sdk import mod, Added
from dataclasses import dataclass

@dataclass
class State:
    accumulated_text: str = ""
    reasoning_ended: bool = False
    response_token_count: int = 0
    injected: bool = False

states: dict[str, State] = {{}}

@mod
def {mod_name}(event, actions, tokenizer):
    st = states.get(event.request_id)
    if not st:
        states[event.request_id] = State()
        st = states[event.request_id]

    if isinstance(event, Added) and not event.forced:
        text = tokenizer.decode(event.added_tokens)
        st.accumulated_text += text

        # Detect </think> tag - reasoning has ended
        if not st.reasoning_ended and "</think>" in st.accumulated_text:
            st.reasoning_ended = True

        # Count tokens while in response (after reasoning)
        if st.reasoning_ended:
            st.response_token_count += len(event.added_tokens)

            if st.response_token_count >= {token_count} and not st.injected:
                st.injected = True
                injection = "{injection_string}"
                tokens = tokenizer.encode(injection, add_special_tokens=False)
                return actions.force_tokens(tokens=tokens)

    return actions.noop()
"#, mod_name = mod_name, injection_string = injection_string, token_count = token_count)
        }

        InjectionPosition::ResponseEnd => {
            format!(r#"from quote_mod_sdk import mod, Added
from dataclasses import dataclass

@dataclass
class State:
    accumulated_text: str = ""
    reasoning_ended: bool = False
    injected: bool = False

states: dict[str, State] = {{}}

@mod
def {mod_name}(event, actions, tokenizer):
    st = states.get(event.request_id)
    if not st:
        states[event.request_id] = State()
        st = states[event.request_id]

    if isinstance(event, Added) and not event.forced and not st.injected:
        text = tokenizer.decode(event.added_tokens)
        st.accumulated_text += text

        # Detect </think> tag - reasoning has ended
        if not st.reasoning_ended and "</think>" in st.accumulated_text:
            st.reasoning_ended = True

        # Only inject at EOS if we're in the response phase
        if st.reasoning_ended:
            if any(marker in text for marker in ['<|eot_id|>', '<|end|>', '</s>', '<|im_end|>']):
                st.injected = True
                injection = "{injection_string}"
                injection_tokens = tokenizer.encode(injection, add_special_tokens=False)
                # Let the model naturally generate EOS after our injection
                return actions.backtrack(
                    steps=len(event.added_tokens),
                    tokens=injection_tokens
                )

    return actions.noop()
"#, mod_name = mod_name, injection_string = injection_string)
        }

        InjectionPosition::ReasoningPhraseReplace => {
            let phrase_pairs = build_phrase_pairs(config, &injection_string);

            format!(r#"from quote_mod_sdk import mod, Added
from dataclasses import dataclass

@dataclass
class State:
    accumulated_text: str = ""
    in_reasoning: bool = False

states: dict[str, State] = {{}}

# Phrase pairs: (detect, replace)
PHRASE_PAIRS = {phrase_pairs}

@mod
def {mod_name}(event, actions, tokenizer):
    st = states.get(event.request_id)
    if not st:
        states[event.request_id] = State()
        st = states[event.request_id]

    if isinstance(event, Added) and not event.forced:
        text = tokenizer.decode(event.added_tokens)
        st.accumulated_text += text

        # Track reasoning phase
        if not st.in_reasoning and "<think>" in st.accumulated_text:
            st.in_reasoning = True
        if st.in_reasoning and "</think>" in st.accumulated_text:
            st.in_reasoning = False

        # Only replace within reasoning phase
        if st.in_reasoning:
            for needle, replacement in PHRASE_PAIRS:
                if st.accumulated_text.endswith(needle):
                    st.accumulated_text = st.accumulated_text[:-len(needle)]
                    needle_tokens = tokenizer.encode(needle, add_special_tokens=False)
                    replacement_tokens = tokenizer.encode(replacement, add_special_tokens=False)
                    return actions.backtrack(
                        steps=len(needle_tokens),
                        tokens=replacement_tokens
                    )

    return actions.noop()
"#, mod_name = mod_name, phrase_pairs = phrase_pairs)
        }

        InjectionPosition::ResponsePhraseReplace => {
            let phrase_pairs = build_phrase_pairs(config, &injection_string);

            format!(r#"from quote_mod_sdk import mod, Added
from dataclasses import dataclass

@dataclass
class State:
    accumulated_text: str = ""
    reasoning_ended: bool = False

states: dict[str, State] = {{}}

# Phrase pairs: (detect, replace)
PHRASE_PAIRS = {phrase_pairs}

@mod
def {mod_name}(event, actions, tokenizer):
    st = states.get(event.request_id)
    if not st:
        states[event.request_id] = State()
        st = states[event.request_id]

    if isinstance(event, Added) and not event.forced:
        text = tokenizer.decode(event.added_tokens)
        st.accumulated_text += text

        # Track when reasoning ends
        if not st.reasoning_ended and "</think>" in st.accumulated_text:
            st.reasoning_ended = True

        # Only replace in response phase (after reasoning)
        if st.reasoning_ended:
            for needle, replacement in PHRASE_PAIRS:
                if st.accumulated_text.endswith(needle):
                    st.accumulated_text = st.accumulated_text[:-len(needle)]
                    needle_tokens = tokenizer.encode(needle, add_special_tokens=False)
                    replacement_tokens = tokenizer.encode(replacement, add_special_tokens=False)
                    return actions.backtrack(
                        steps=len(needle_tokens),
                        tokens=replacement_tokens
                    )

    return actions.noop()
"#, mod_name = mod_name, phrase_pairs = phrase_pairs)
        }

        InjectionPosition::FullStreamPhraseReplace => {
            let phrase_pairs = build_phrase_pairs(config, &injection_string);

            format!(r#"from quote_mod_sdk import mod, Added
from dataclasses import dataclass

@dataclass
class State:
    accumulated_text: str = ""

states: dict[str, State] = {{}}

# Phrase pairs: (detect, replace)
PHRASE_PAIRS = {phrase_pairs}

@mod
def {mod_name}(event, actions, tokenizer):
    st = states.get(event.request_id)
    if not st:
        states[event.request_id] = State()
        st = states[event.request_id]

    if isinstance(event, Added) and not event.forced:
        text = tokenizer.decode(event.added_tokens)
        st.accumulated_text += text

        # Check each phrase pair
        for needle, replacement in PHRASE_PAIRS:
            if st.accumulated_text.endswith(needle):
                st.accumulated_text = st.accumulated_text[:-len(needle)]
                needle_tokens = tokenizer.encode(needle, add_special_tokens=False)
                replacement_tokens = tokenizer.encode(replacement, add_special_tokens=False)
                return actions.backtrack(
                    steps=len(needle_tokens),
                    tokens=replacement_tokens
                )

    return actions.noop()
"#, mod_name = mod_name, phrase_pairs = phrase_pairs)
        }
    }
}

/// Request body for uploading a mod
#[derive(Debug, Deserialize)]
pub struct UploadModRequest {
    /// The model to upload to
    pub model: String,
    /// The mod code
    pub code: String,
    /// The mod name
    pub mod_name: String,
}

/// Response for uploading a mod
#[derive(Debug, Serialize)]
pub struct UploadModResponse {
    /// Whether the upload succeeded
    pub success: bool,
    /// The mod name
    pub mod_name: String,
    /// Message
    pub message: String,
}

/// Upload a mod to a model server
///
/// POST /playground/mods/upload
/// Headers:
///   X-API-Key: <api_key>
pub async fn upload_mod(
    headers: HeaderMap,
    Json(request): Json<UploadModRequest>,
) -> Result<Json<UploadModResponse>, (StatusCode, Json<serde_json::Value>)> {
    let api_key = extract_api_key_from_headers(&headers).ok_or_else(|| {
        (
            StatusCode::UNAUTHORIZED,
            Json(serde_json::json!({
                "error": "API key required",
                "code": 401
            })),
        )
    })?;

    let endpoints = ModelEndpoints::from_env();

    let endpoint = resolve_model_endpoint(&endpoints, &request.model)?;

    // Get admin key for registering with model server
    let admin_key = env::var("PLAYGROUND_ADMIN_KEY").map_err(|_| {
        (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(serde_json::json!({
                "error": "Playground not configured. PLAYGROUND_ADMIN_KEY not set.",
                "code": 500
            })),
        )
    })?;

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(60))
        .build()
        .unwrap_or_default();

    // Register the API key with this model server first
    register_key_with_server(&client, endpoint, &api_key, &admin_key).await?;

    let upload_url = format!("{}/v1/mods", endpoint);

    let payload = serde_json::json!({
        "name": request.mod_name,
        "language": "python",
        "module": "client_mod",
        "entrypoint": request.mod_name,
        "source": request.code,
        "user_api_key": api_key
    });

    let response = client
        .post(&upload_url)
        .header("X-User-Api-Key", &api_key)
        .json(&payload)
        .send()
        .await
        .map_err(|e| {
            (
                StatusCode::BAD_GATEWAY,
                Json(serde_json::json!({
                    "error": format!("Failed to upload mod: {}", e),
                    "code": 502
                })),
            )
        })?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err((
            StatusCode::BAD_GATEWAY,
            Json(serde_json::json!({
                "error": format!("Model server rejected mod upload: {} - {}", status, body),
                "code": 502
            })),
        ));
    }

    Ok(Json(UploadModResponse {
        success: true,
        mod_name: request.mod_name,
        message: "Mod uploaded successfully".to_string(),
    }))
}

/// Chat message for inference
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatMessage {
    pub role: String,
    pub content: String,
}

/// Request body for running inference
#[derive(Debug, Deserialize)]
pub struct RunInferenceRequest {
    /// The model to use
    pub model: String,
    /// The mod name (optional, if mod should be activated)
    pub mod_name: Option<String>,
    /// Chat messages
    pub messages: Vec<ChatMessage>,
    /// Max tokens to generate
    pub max_tokens: Option<u32>,
    /// Temperature
    pub temperature: Option<f32>,
    /// Whether to extract SAE features after inference
    pub extract_features: Option<bool>,
}

/// A feature activation entry
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FeatureActivation {
    pub id: i64,
    pub activation: f64,
}

/// A single position in the feature timeline
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FeatureTimelineEntry {
    pub position: usize,
    pub token: i64,
    pub token_str: String,
    pub top_features: Vec<FeatureActivation>,
}

/// Response for running inference
#[derive(Debug, Serialize)]
pub struct RunInferenceResponse {
    /// The generated text
    pub text: String,
    /// The request ID for fetching detailed logs
    pub request_id: Option<String>,
    /// Full response from the model server
    pub raw_response: serde_json::Value,
    /// Feature timeline (if extract_features was true)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub feature_timeline: Option<Vec<FeatureTimelineEntry>>,
}

/// Run inference on a model server
///
/// POST /playground/inference
/// Headers:
///   X-API-Key: <api_key>
pub async fn run_inference(
    headers: HeaderMap,
    Json(request): Json<RunInferenceRequest>,
) -> Result<Json<RunInferenceResponse>, (StatusCode, Json<serde_json::Value>)> {
    let api_key = extract_api_key_from_headers(&headers).ok_or_else(|| {
        (
            StatusCode::UNAUTHORIZED,
            Json(serde_json::json!({
                "error": "API key required",
                "code": 401
            })),
        )
    })?;

    let endpoints = ModelEndpoints::from_env();

    let endpoint = resolve_model_endpoint(&endpoints, &request.model)?;

    let base_model_id = endpoints.get_model_id(&request.model).ok_or_else(|| {
        (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({
                "error": format!("Unknown model: {}", request.model),
                "code": 400
            })),
        )
    })?;

    // If a mod is specified, append it to the model ID
    let model_id = if let Some(ref mod_name) = request.mod_name {
        format!("{}/{}", base_model_id, mod_name)
    } else {
        base_model_id.to_string()
    };

    let inference_url = format!("{}/v1/chat/completions", endpoint);
    let client = reqwest::Client::new();

    let mut payload = serde_json::json!({
        "model": model_id,
        "messages": request.messages,
        "user_api_key": api_key
    });

    if let Some(max_tokens) = request.max_tokens {
        payload["max_tokens"] = serde_json::json!(max_tokens);
    }
    if let Some(temperature) = request.temperature {
        payload["temperature"] = serde_json::json!(temperature);
    }

    let response = client
        .post(&inference_url)
        .header("X-User-Api-Key", &api_key)
        .json(&payload)
        .send()
        .await
        .map_err(|e| {
            (
                StatusCode::BAD_GATEWAY,
                Json(serde_json::json!({
                    "error": format!("Failed to run inference: {}", e),
                    "code": 502
                })),
            )
        })?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err((
            StatusCode::BAD_GATEWAY,
            Json(serde_json::json!({
                "error": format!("Inference failed: {} - {}", status, body),
                "code": 502
            })),
        ));
    }

    let raw_response: serde_json::Value = response.json().await.map_err(|e| {
        (
            StatusCode::BAD_GATEWAY,
            Json(serde_json::json!({
                "error": format!("Failed to parse inference response: {}", e),
                "code": 502
            })),
        )
    })?;

    tracing::info!("Raw inference response: {:?}", raw_response);

    // Extract the generated text from the response
    let text = raw_response["choices"][0]["message"]["content"]
        .as_str()
        .unwrap_or("")
        .to_string();

    // Try to extract request_id from response if available
    // Modal servers may use different field names
    let request_id = raw_response["request_id"]
        .as_str()
        .or_else(|| raw_response["x_request_id"].as_str())
        .or_else(|| raw_response["concordance_request_id"].as_str())
        .or_else(|| raw_response["id"].as_str())
        .map(|s| s.to_string());
    
    tracing::info!("Extracted request_id: {:?}", request_id);

    // Optionally extract features if requested
    let feature_timeline = if request.extract_features.unwrap_or(false) {
        // Feature extraction is only supported for Llama models currently
        if request.model == "llama-3.1-8b" {
            // We need to get the token sequence - try to extract from log data
            // For now, we'll call the feature extraction endpoint separately
            // This is a placeholder - actual implementation would need the token IDs
            tracing::info!("Feature extraction requested but requires separate call to /extract_features endpoint with token IDs");
            None
        } else {
            tracing::info!("Feature extraction not supported for model: {}", request.model);
            None
        }
    } else {
        None
    };

    Ok(Json(RunInferenceResponse {
        text,
        request_id,
        raw_response,
        feature_timeline,
    }))
}

/// Request body for extracting features
#[derive(Debug, Deserialize)]
pub struct ExtractFeaturesRequest {
    /// The model to use for feature extraction
    pub model: String,
    /// List of token IDs to analyze
    pub tokens: Vec<i64>,
    /// Number of top features to return per position (default: 20)
    pub top_k: Option<usize>,
    /// Layer to extract features from (default: 16)
    pub layer: Option<usize>,
    /// Positions where injections occurred (for before/after comparison)
    pub injection_positions: Option<Vec<usize>>,
}

/// Response for feature extraction
#[derive(Debug, Serialize)]
pub struct ExtractFeaturesResponse {
    /// Feature timeline for each position
    pub feature_timeline: Vec<FeatureTimelineEntry>,
    /// Before/after comparisons at injection points (if injection_positions provided)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub comparisons: Option<Vec<serde_json::Value>>,
}

/// Request body for analyzing features with Claude
#[derive(Debug, Deserialize)]
pub struct AnalyzeFeaturesRequest {
    /// The model (for routing to correct endpoint)
    pub model: String,
    /// Feature timeline from extract_features
    pub feature_timeline: Vec<serde_json::Value>,
    /// Positions where injections occurred
    pub injection_positions: Option<Vec<usize>>,
    /// Additional context about the experiment
    pub context: Option<String>,
    /// Layer the features were extracted from
    pub layer: Option<usize>,
}

/// Feature with description from Neuronpedia
#[derive(Debug, Serialize, Deserialize)]
pub struct FeatureWithDescription {
    pub id: i64,
    pub activation: f64,
    pub description: String,
}

/// Response for feature analysis
#[derive(Debug, Serialize)]
pub struct AnalyzeFeaturesResponse {
    /// Claude's analysis of the feature patterns
    pub analysis: String,
    /// Top features with their Neuronpedia descriptions
    pub top_features: Vec<FeatureWithDescription>,
}

/// Extract SAE features for a token sequence
///
/// POST /playground/features/extract
/// Headers:
///   X-API-Key: <api_key>
pub async fn extract_features(
    headers: HeaderMap,
    Json(request): Json<ExtractFeaturesRequest>,
) -> Result<Json<ExtractFeaturesResponse>, (StatusCode, Json<serde_json::Value>)> {
    let _api_key = extract_api_key_from_headers(&headers).ok_or_else(|| {
        (
            StatusCode::UNAUTHORIZED,
            Json(serde_json::json!({
                "error": "API key required",
                "code": 401
            })),
        )
    })?;

    // Feature extraction is only supported for Llama models currently
    if request.model != "llama-3.1-8b" {
        return Err((
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({
                "error": format!("Feature extraction not supported for model: {}. Only llama-3.1-8b is currently supported.", request.model),
                "code": 400
            })),
        ));
    }

    let endpoints = ModelEndpoints::from_env();

    let endpoint = endpoints.get_sae_url().ok_or_else(|| {
        (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(serde_json::json!({
                "error": "SAE analysis service not configured",
                "code": 503
            })),
        )
    })?;

    // Call the feature extraction endpoint on the SAE server
    let extract_url = format!("{}/extract_features", endpoint);
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(120))  // Feature extraction can take time
        .build()
        .unwrap_or_default();

    let mut payload = serde_json::json!({
        "tokens": request.tokens,
    });

    if let Some(top_k) = request.top_k {
        payload["top_k"] = serde_json::json!(top_k);
    }
    if let Some(layer) = request.layer {
        payload["layer"] = serde_json::json!(layer);
    }
    if let Some(ref injection_positions) = request.injection_positions {
        payload["injection_positions"] = serde_json::json!(injection_positions);
    }

    tracing::info!("Calling feature extraction endpoint: {}", extract_url);

    let response = client
        .post(&extract_url)
        .json(&payload)
        .send()
        .await
        .map_err(|e| {
            tracing::error!("Failed to call feature extraction: {}", e);
            (
                StatusCode::BAD_GATEWAY,
                Json(serde_json::json!({
                    "error": format!("Failed to extract features: {}", e),
                    "code": 502
                })),
            )
        })?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        tracing::error!("Feature extraction failed: {} - {}", status, body);
        return Err((
            StatusCode::BAD_GATEWAY,
            Json(serde_json::json!({
                "error": format!("Feature extraction failed: {} - {}", status, body),
                "code": 502
            })),
        ));
    }

    let raw_response: serde_json::Value = response.json().await.map_err(|e| {
        (
            StatusCode::BAD_GATEWAY,
            Json(serde_json::json!({
                "error": format!("Failed to parse feature extraction response: {}", e),
                "code": 502
            })),
        )
    })?;

    // Parse the feature timeline from the response
    let feature_timeline: Vec<FeatureTimelineEntry> = raw_response["feature_timeline"]
        .as_array()
        .map(|arr| {
            arr.iter()
                .filter_map(|entry| {
                    Some(FeatureTimelineEntry {
                        position: entry["position"].as_u64()? as usize,
                        token: entry["token"].as_i64()?,
                        token_str: entry["token_str"].as_str()?.to_string(),
                        top_features: entry["top_features"]
                            .as_array()?
                            .iter()
                            .filter_map(|f| {
                                Some(FeatureActivation {
                                    id: f["id"].as_i64()?,
                                    activation: f["activation"].as_f64()?,
                                })
                            })
                            .collect(),
                    })
                })
                .collect()
        })
        .unwrap_or_default();

    // Parse comparisons if present
    let comparisons = raw_response["comparisons"]
        .as_array()
        .map(|arr| arr.clone());

    Ok(Json(ExtractFeaturesResponse {
        feature_timeline,
        comparisons,
    }))
}

/// Analyze SAE features using Claude
///
/// POST /playground/features/analyze
/// Headers:
///   X-API-Key: <api_key>
pub async fn analyze_features(
    headers: HeaderMap,
    Json(request): Json<AnalyzeFeaturesRequest>,
) -> Result<Json<AnalyzeFeaturesResponse>, (StatusCode, Json<serde_json::Value>)> {
    let api_key = extract_api_key_from_headers(&headers).ok_or_else(|| {
        (
            StatusCode::UNAUTHORIZED,
            Json(serde_json::json!({
                "error": "API key required",
                "code": 401
            })),
        )
    })?;

    // Rate limit: 5 requests per 60s per API key
    check_rate_limit(&api_key).map_err(|_| {
        (
            StatusCode::TOO_MANY_REQUESTS,
            Json(serde_json::json!({
                "error": "Rate limit exceeded. Max 5 analysis requests per 60 seconds.",
                "code": 429
            })),
        )
    })?;

    // Only supported for Llama models
    if request.model != "llama-3.1-8b" {
        return Err((
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({
                "error": format!("Feature analysis not supported for model: {}", request.model),
                "code": 400
            })),
        ));
    }

    let endpoints = ModelEndpoints::from_env();

    let endpoint = endpoints.get_sae_url().ok_or_else(|| {
        (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(serde_json::json!({
                "error": "SAE analysis service not configured",
                "code": 503
            })),
        )
    })?;

    // Call the analyze_features endpoint on the SAE server
    let analyze_url = format!("{}/analyze_features", endpoint);
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .build()
        .unwrap_or_default();

    let mut payload = serde_json::json!({
        "feature_timeline": request.feature_timeline,
    });

    if let Some(ref positions) = request.injection_positions {
        payload["injection_positions"] = serde_json::json!(positions);
    }
    if let Some(ref context) = request.context {
        payload["context"] = serde_json::json!(context);
    }
    if let Some(layer) = request.layer {
        payload["layer"] = serde_json::json!(layer);
    }

    tracing::info!("Calling feature analysis endpoint: {}", analyze_url);

    let response = client
        .post(&analyze_url)
        .json(&payload)
        .send()
        .await
        .map_err(|e| {
            tracing::error!("Failed to call feature analysis: {}", e);
            (
                StatusCode::BAD_GATEWAY,
                Json(serde_json::json!({
                    "error": format!("Failed to analyze features: {}", e),
                    "code": 502
                })),
            )
        })?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        tracing::error!("Feature analysis failed: {} - {}", status, body);
        return Err((
            StatusCode::BAD_GATEWAY,
            Json(serde_json::json!({
                "error": format!("Feature analysis failed: {} - {}", status, body),
                "code": 502
            })),
        ));
    }

    let raw_response: serde_json::Value = response.json().await.map_err(|e| {
        (
            StatusCode::BAD_GATEWAY,
            Json(serde_json::json!({
                "error": format!("Failed to parse analysis response: {}", e),
                "code": 502
            })),
        )
    })?;

    let analysis = raw_response["analysis"]
        .as_str()
        .unwrap_or("No analysis available")
        .to_string();

    let top_features: Vec<FeatureWithDescription> = raw_response["top_features"]
        .as_array()
        .map(|arr| {
            arr.iter()
                .filter_map(|f| {
                    Some(FeatureWithDescription {
                        id: f["id"].as_i64()?,
                        activation: f["activation"].as_f64()?,
                        description: f["description"].as_str()?.to_string(),
                    })
                })
                .collect()
        })
        .unwrap_or_default();

    Ok(Json(AnalyzeFeaturesResponse {
        analysis,
        top_features,
    }))
}
