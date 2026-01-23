# Inference Engine → Backend API Documentation

## Overview

This document describes the data format expected by the Thunder backend's `/ingest` endpoint. The inference engine accumulator should collect event data during execution and POST it to this endpoint when the request completes.

---

## Endpoint

**URL:** `POST http://localhost:6767/ingest`  
**Content-Type:** `application/json`  
**Success Response:** `201 Created` (empty body)

---

## Payload Structure

The payload consists of 5 main sections that describe a single inference request:

```json
{
  "request": { ... },      // Top-level request metadata
  "events": [ ... ],       // Array of mod events during execution
  "mod_calls": [ ... ],    // Array of mod invocations
  "mod_logs": [ ... ],     // Array of log messages from mods
  "actions": [ ... ]       // Array of actions returned by mods
}
```

---

## 1. Request Object

Top-level metadata about the inference request.

```json
{
  "request_id": "string",           // REQUIRED: Unique identifier for this request
  "created_at": "ISO8601",          // Optional: Request start time (defaults to now)
  "completed_at": "ISO8601",        // Optional: Request completion time
  "model": "string",                // Optional: Model name (e.g., "gemini-2.0-flash")
  "user_api_key": "string",         // Optional: User identifier
  "max_tokens": integer,            // Optional: Max tokens to generate
  "temperature": float,             // Optional: Sampling temperature
  "mod_text": "string"              // Optional: Mod code/name being used
}
```

**Field Notes:**
- `request_id` - Must be unique across all requests. Use UUID or request identifier from your engine
- Timestamps should be ISO8601 format with timezone (e.g., `"2025-12-01T18:30:00Z"`)
- All fields except `request_id` are optional

---

## 2. Events Array

An ordered array of events that occurred during inference. Each event corresponds to one of the 4 event types in the mod system.

**Event Types:**
- `Prefilled` - Initial prompt processing
- `ForwardPass` - Model forward pass for next token prediction  
- `Sampled` - Token was sampled from distribution
- `Added` - Token(s) were added to the sequence

```json
{
  "event_type": "Prefilled" | "ForwardPass" | "Added" | "Sampled",  // REQUIRED
  "step": integer,                  // REQUIRED: Generation step number
  "sequence_order": integer,        // REQUIRED: Global sequence order for replay
  "created_at": "ISO8601",          // Optional: Event timestamp
  "details": {},                    // Optional: Full event object (stored as JSON)
  
  // Prefilled-specific fields:
  "prompt_length": integer,         // Length of initial prompt
  "tokens_so_far_len": integer,     // Current token count
  "max_steps": integer,             // Maximum generation steps
  
  // ForwardPass-specific fields:
  "input_text": "string",           // Last 70 chars of input (for debugging)
  "top_tokens": [                   // Top K tokens with probabilities
    {"token": integer, "prob": float}
  ],
  
  // Sampled-specific fields:
  "sampled_token": integer,         // Token ID that was sampled
  "token_text": "string",           // Decoded token text
  
  // Added-specific fields:
  "added_tokens": [integer],        // Array of token IDs added
  "added_token_count": integer,     // Count of tokens added
  "forced": boolean                 // Whether tokens were forced by mod
}
```

**Important:**
- `sequence_order` must be globally unique and sequential (0, 1, 2, ...) across all events
- Only populate fields relevant to the event type (e.g., `Sampled` events should have `sampled_token`)
- `top_tokens` can be stored as any JSON structure - example shows `[{token, prob}]` format

---

## 3. Mod Calls Array

Records each time a mod is invoked for an event. Multiple mods can be called for a single event.

```json
{
  "event_sequence_order": integer,  // REQUIRED: Links to event via sequence_order
  "mod_name": "string",             // REQUIRED: Name of the mod
  "event_type": "Prefilled" | "ForwardPass" | "Added" | "Sampled",  // REQUIRED
  "step": integer,                  // REQUIRED: Generation step
  "created_at": "ISO8601",          // Optional: When mod was called
  "execution_time_ms": float,       // Optional: Execution time in milliseconds
  "exception_occurred": boolean,    // Optional: Whether mod threw exception (default: false)
  "exception_message": "string",    // Optional: Exception message if error
  "exception_traceback": "string"   // Optional: Full traceback
}
```

**Important:**
- `event_sequence_order` must match the `sequence_order` of an event in the `events` array
- This creates a foreign key relationship: `mod_calls` → `events`
- Track execution time for performance monitoring
- Capture exceptions for debugging

---

## 4. Mod Logs Array

Captures all log output from mods (print statements, logging calls).

```json
{
  "mod_call_sequence": integer,     // REQUIRED: Index into mod_calls array
  "mod_name": "string",             // REQUIRED: Name of the mod
  "log_message": "string",          // REQUIRED: Full log message
  "log_level": "DEBUG" | "INFO" | "WARNING" | "ERROR",  // Optional: default "INFO"
  "created_at": "ISO8601"           // Optional: Log timestamp
}
```

**Important:**
- `mod_call_sequence` is the **index** (0-based) into the `mod_calls` array
- Example: If you want to attach a log to the 3rd mod call, use `"mod_call_sequence": 2`
- All print/log output from mods should be captured here

---

## 5. Actions Array

Records all actions returned by mods. Actions are what mods return to modify inference behavior.

**Action Types:**
- `Noop` - No operation
- `AdjustedPrefill` - Modified the prompt
- `ForceTokens` - Forced specific tokens
- `ForceOutput` - Forced output text
- `Backtrack` - Backtracked and replaced tokens
- `AdjustedLogits` - Modified logit distribution
- `ToolCalls` - Triggered tool calls
- `EmitError` - Emitted an error

```json
{
  "mod_call_sequence": integer,     // REQUIRED: Index into mod_calls array
  "action_type": "Noop" | "AdjustedPrefill" | ...,  // REQUIRED
  "action_order": integer,          // REQUIRED: Order if multiple actions from same mod
  "created_at": "ISO8601",          // Optional: Action timestamp
  "details": {},                    // Optional: Full action object (stored as JSON)
  
  // AdjustedPrefill-specific:
  "new_prompt": "string",           // New prompt text
  "new_length": integer,            // New prompt length
  "adjusted_max_steps": integer,    // Adjusted max steps
  
  // ForceTokens/ForceOutput-specific:
  "token_count": integer,           // Number of forced tokens
  "tokens_preview": "string",       // First 10 tokens as readable string
  
  // Backtrack-specific:
  "backtrack_steps": integer,       // Number of steps to backtrack
  "backtrack_token_count": integer, // Number of replacement tokens
  
  // AdjustedLogits-specific:
  "logits_shape": "string",         // Shape of logits tensor (e.g., "[1, 32000]")
  "temperature": float,             // Temperature override
  
  // ToolCalls-specific:
  "has_tool_calls": boolean,        // Whether tool calls present
  "tool_calls": {},                 // Full tool call payload (stored as JSON)
  
  // EmitError-specific:
  "error_message": "string"         // Error message
}
```

**Important:**
- `mod_call_sequence` is the **index** into the `mod_calls` array
- `action_order` allows multiple actions from same mod (usually 0)
- Only populate fields relevant to the action type

---

## Relationship Diagram

```
request (1)
  ├─→ events (N)
        └─→ mod_calls (N)
              ├─→ mod_logs (N)
              └─→ actions (N)
```

**Key Points:**
- Each `mod_call` links to an `event` via `event_sequence_order`
- Each `mod_log` links to a `mod_call` via `mod_call_sequence` (array index)
- Each `action` links to a `mod_call` via `mod_call_sequence` (array index)
- The `sequence_order` in events is the bridge between events and mod_calls

---

## Complete Example

```json
{
  "request": {
    "request_id": "req_abc123",
    "created_at": "2025-12-01T18:30:00Z",
    "completed_at": "2025-12-01T18:30:05Z",
    "model": "gemini-2.0-flash",
    "user_api_key": "user_789",
    "max_tokens": 1000,
    "temperature": 0.7,
    "mod_text": "sample_mod.py"
  },
  "events": [
    {
      "event_type": "Prefilled",
      "step": 0,
      "sequence_order": 0,
      "prompt_length": 150,
      "tokens_so_far_len": 0,
      "max_steps": 500
    },
    {
      "event_type": "ForwardPass",
      "step": 1,
      "sequence_order": 1,
      "input_text": "Once upon a time",
      "top_tokens": [
        {"token": 1234, "prob": 0.85},
        {"token": 5678, "prob": 0.10}
      ]
    },
    {
      "event_type": "Sampled",
      "step": 1,
      "sequence_order": 2,
      "sampled_token": 1234,
      "token_text": " there"
    },
    {
      "event_type": "Added",
      "step": 1,
      "sequence_order": 3,
      "added_tokens": [1234],
      "added_token_count": 1,
      "forced": false
    }
  ],
  "mod_calls": [
    {
      "event_sequence_order": 0,
      "mod_name": "sample_mod",
      "event_type": "Prefilled",
      "step": 0,
      "execution_time_ms": 2.5,
      "exception_occurred": false
    },
    {
      "event_sequence_order": 1,
      "mod_name": "sample_mod",
      "event_type": "ForwardPass",
      "step": 1,
      "execution_time_ms": 1.2,
      "exception_occurred": false
    }
  ],
  "mod_logs": [
    {
      "mod_call_sequence": 0,
      "mod_name": "sample_mod",
      "log_message": "Prefill event processed successfully",
      "log_level": "INFO"
    },
    {
      "mod_call_sequence": 1,
      "mod_name": "sample_mod",
      "log_message": "Forward pass complete, top token prob: 0.85",
      "log_level": "DEBUG"
    }
  ],
  "actions": [
    {
      "mod_call_sequence": 0,
      "action_type": "Noop",
      "action_order": 0
    },
    {
      "mod_call_sequence": 1,
      "action_type": "AdjustedLogits",
      "action_order": 0,
      "logits_shape": "[1, 32000]",
      "temperature": 0.8
    }
  ]
}
```

---

## Implementation Checklist for Accumulator

- [ ] Track `sequence_order` counter globally across all events (0, 1, 2, ...)
- [ ] For each event, record event type and step number
- [ ] For each mod invocation, record which event triggered it (via `event_sequence_order`)
- [ ] Capture mod execution time using timers
- [ ] Intercept all mod print/log statements and store in `mod_logs`
- [ ] Record all actions returned by mods
- [ ] Link logs and actions to their mod_call using array indices
- [ ] Generate unique `request_id` for each inference request
- [ ] POST complete payload to `/ingest` endpoint when request completes
- [ ] Handle errors (backend returns 4xx/5xx for malformed data)

---

## Testing

Use the provided `sample_payload.json` to test:

```bash
curl -X POST http://localhost:6767/ingest \
  -H "Content-Type: application/json" \
  -d @sample_payload.json \
  -w "\nHTTP Status: %{http_code}\n"
```

Expected: `HTTP Status: 201`

---

## Notes

- All timestamps should be ISO8601 with timezone (UTC recommended)
- The `details` fields allow storing complete event/action objects as JSON for future analysis
- Array indices (`mod_call_sequence`) are 0-based
- Empty arrays are allowed for any of the array fields
- Backend validates foreign key relationships (e.g., `event_sequence_order` must exist)
