// API Response Types for Concordance Backend

export interface ListLogsResponse {
  data: LogSummary[];
  limit: number;
  offset: number;
  returned: number;
}

export interface LogSummary {
  request_id: string;
  created_ts: string;
  finished_ts: string | null;
  model_id: string | null;
  user_api_key: string | null;
  final_text: string | null;
  total_steps: number;
  favorited_by: string[];
  discussion_count: number;
}

export interface LogResponse {
  request_id: string;
  created_ts: string;
  finished_ts: string | null;
  system_prompt: string | null;
  user_prompt: string | null;
  formatted_prompt: string | null;
  model_id: string | null;
  user_api_key: string | null;
  is_public: boolean;
  public_token: string | null;
  model_version: string | null;
  tokenizer_version: string | null;
  vocab_hash: string | null;
  sampler_preset: string | null;
  sampler_algo: string | null;
  rng_seed: number | null;
  max_steps: number | null;
  active_mod: ActiveMod | null;
  final_tokens: number[] | null;
  final_text: string | null;
  sequence_confidence: number | null;
  eos_reason: string | null;
  request_tags: Record<string, unknown>;
  favorited_by: string[];
  tags: string[];
  // New structured trace data (optional for backwards compatibility)
  events?: EventLog[];
  mod_calls?: ModCallLog[];
  mod_logs?: ModLogEntry[];
  actions?: ActionLog[];
  // Legacy fields
  steps?: LogStep[];
  step_logit_summaries: StepLogitSummaryLog[];
  inference_stats: RequestInferenceStatsLog | null;
  discussion_count: number;
}

export interface ActiveMod {
  id: number;
  name: string | null;
}

// Event types from the database
export type EventType = "Prefilled" | "ForwardPass" | "Sampled" | "Added";

export interface EventLog {
  id: number;
  event_type: EventType | string; // Backend returns string, accept both
  step: number;
  sequence_order: number;
  created_at: string;
  // Prefilled fields
  prompt_length: number | null;
  max_steps: number | null;
  // ForwardPass fields
  input_text: string | null;
  top_tokens: TopToken[] | null;
  // Sampled fields
  sampled_token: number | null;
  token_text: string | null;
  // Added fields
  added_tokens: number[] | null;
  added_token_count: number | null;
  forced: boolean | null;
}

export interface TopToken {
  token: number;
  token_str: string;
  logprob: number;
  prob?: number;
}

export interface ModCallLog {
  id: number;
  event_id: number;
  mod_name: string;
  event_type: string;
  step: number;
  created_at: string;
  execution_time_ms: number | null;
  exception_occurred: boolean;
  exception_message: string | null;
}

export interface ModLogEntry {
  id: number;
  mod_call_id: number;
  mod_name: string;
  log_message: string;
  log_level: LogLevel;
  created_at: string;
}

export type LogLevel = "DEBUG" | "INFO" | "WARNING" | "ERROR";

// Action types
export type ActionType =
  | "Noop"
  | "AdjustedPrefill"
  | "ForceTokens"
  | "ForceOutput"
  | "Backtrack"
  | "AdjustedLogits"
  | "ToolCalls"
  | "EmitError";

export interface ActionLog {
  action_id: number;
  step_index: number | null;
  mod_id: number | null;
  block_id: number | null;
  block_key: string | null;
  action_type: ActionType;
  event: string | null;
  payload: ActionPayload;
  created_at: string;
}

export interface ActionPayload {
  // ForceTokens / ForceOutput / AdjustedPrefill / Backtrack
  tokens?: number[];
  tokens_as_text?: string[];
  token_count?: number;
  // AdjustedPrefill
  adjusted_max_steps?: number;
  // Backtrack
  backtrack_steps?: number;
  // AdjustedLogits
  logits_shape?: number[];
  temperature?: number;
  note?: string;
  // ToolCalls
  tool_calls?: unknown;
  // EmitError
  error_message?: string;
  // Generic
  [key: string]: unknown;
}

// Legacy LogStep type for backwards compatibility
export interface LogStep {
  step_index: number;
  token: number | null;
  token_text: string | null;
  forced: boolean;
  forced_by: string | null;
  adjusted_logits: boolean;
  top_k: number | null;
  top_p: number | null;
  temperature: number | null;
  prob: number | null;
  logprob: number | null;
  entropy: number | null;
  flatness: number | null;
  surprisal: number | null;
  cum_nll: number | null;
  rng_counter: number | null;
  created_at: string;
}

export interface StepLogitSummaryLog {
  id: number;
  step_index: number;
  phase: string | null;
  topk: Record<string, unknown>;
  top_p_cutoff: number | null;
  top_p_count: number | null;
  note: string | null;
  created_at: string;
}

export interface RequestInferenceStatsLog {
  prompt_tokens: number | null;
  generated_tokens: number | null;
  total_tokens: number | null;
  wall_time_ms: number | null;
  avg_tokens_per_sec: number | null;
  max_tokens_per_sec: number | null;
  queue_latency_ms: number | null;
  scheduler_latency_ms: number | null;
  prefill_latency_ms: number | null;
  decode_latency_ms: number | null;
  postprocess_latency_ms: number | null;
  estimated_cost_usd: number | null;
  compute_node: string | null;
  device_type: string | null;
  captured_at: string;
}

// Tree node types for visualization
export interface TraceTreeNode {
  id: string;
  type: "step" | "event" | "mod_call" | "action" | "log";
  label: string;
  data: EventLog | ModCallLog | ActionLog | ModLogEntry;
  children: TraceTreeNode[];
  metadata?: {
    step?: number;
    sequence_order?: number;
    timestamp?: string;
    duration_ms?: number;
    has_error?: boolean;
  };
}
