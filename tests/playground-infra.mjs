#!/usr/bin/env node
/**
 * Concordance Playground Infrastructure Test Suite
 *
 * Hits the REAL production API to verify the full playground flow works:
 *   API key generation -> mod generation -> mod upload -> inference -> SAE feature extraction -> analysis
 *
 * Usage:
 *   node tests/playground-infra.mjs                              # test against production
 *   API_BASE=http://localhost:6767 node tests/playground-infra.mjs  # test against local
 *
 * Requirements: Node >= 18 (uses built-in fetch)
 */

const API_BASE = process.env.API_BASE || "https://research.concordance.co/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let passed = 0;
let failed = 0;
let skipped = 0;
const failures = [];

const BOLD = "\x1b[1m";
const GREEN = "\x1b[32m";
const RED = "\x1b[31m";
const YELLOW = "\x1b[33m";
const DIM = "\x1b[2m";
const RESET = "\x1b[0m";

function ok(name, detail) {
  passed++;
  console.log(`  ${GREEN}PASS${RESET}  ${name}${detail ? `  ${DIM}${detail}${RESET}` : ""}`);
}

function fail(name, reason) {
  failed++;
  failures.push({ name, reason });
  console.log(`  ${RED}FAIL${RESET}  ${name}  ${RED}${reason}${RESET}`);
}

function skip(name, reason) {
  skipped++;
  console.log(`  ${YELLOW}SKIP${RESET}  ${name}  ${DIM}${reason}${RESET}`);
}

function section(title) {
  console.log(`\n${BOLD}--- ${title} ---${RESET}`);
}

async function post(path, body, headers = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch {
    json = null;
  }
  return { status: res.status, ok: res.ok, json, text };
}

async function get(path, headers = {}) {
  const res = await fetch(`${API_BASE}${path}`, { headers });
  const text = await res.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch {
    json = null;
  }
  return { status: res.status, ok: res.ok, json, text };
}

// ---------------------------------------------------------------------------
// State accumulated across tests
// ---------------------------------------------------------------------------

let apiKey = null;
let llamaModCode = null;
let qwenModCode = null;
let llamaInferenceText = null;
let llamaRequestId = null;
let qwenInferenceText = null;

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

async function testHealth() {
  section("Health & Connectivity");
  try {
    const res = await get("/health");
    if (res.ok) {
      ok("GET /health returns 200");
    } else {
      fail("GET /health returns 200", `status ${res.status}`);
    }
  } catch (e) {
    fail("GET /health returns 200", `network error: ${e.message}`);
  }
}

async function testApiKeyGeneration() {
  section("API Key Generation");
  try {
    const res = await post("/playground/api-key", { session_id: "infra_test" });
    if (!res.ok) {
      fail("POST /playground/api-key succeeds", `status ${res.status}: ${res.text}`);
      return;
    }
    if (!res.json?.api_key || typeof res.json.api_key !== "string") {
      fail("Response contains api_key string", JSON.stringify(res.json));
      return;
    }
    if (!res.json?.message) {
      fail("Response contains message", JSON.stringify(res.json));
      return;
    }
    apiKey = res.json.api_key;
    ok("POST /playground/api-key succeeds", `key prefix: ${apiKey.slice(0, 8)}...`);
    ok("Response shape: { api_key, message }");
  } catch (e) {
    fail("POST /playground/api-key succeeds", e.message);
  }
}

async function testModGeneration() {
  section("Mod Code Generation");

  // Test: start position (simplest)
  try {
    const res = await post("/playground/mods/generate", {
      config: {
        injection_string: "WAIT --",
        position: "start",
      },
    });
    if (!res.ok) {
      fail("Generate mod (start position)", `status ${res.status}: ${res.text}`);
    } else if (!res.json?.code || !res.json?.mod_name) {
      fail("Generate mod (start position) shape", JSON.stringify(res.json));
    } else {
      llamaModCode = res.json.code;
      ok("Generate mod (start position)", `${res.json.code.length} chars of Python`);
    }
  } catch (e) {
    fail("Generate mod (start position)", e.message);
  }

  // Test: after_tokens position
  try {
    const res = await post("/playground/mods/generate", {
      config: {
        injection_string: "HOLD ON --",
        position: "after_tokens",
        token_count: 10,
      },
    });
    if (res.ok && res.json?.code) {
      ok("Generate mod (after_tokens, token_count=10)");
    } else {
      fail("Generate mod (after_tokens)", `status ${res.status}: ${res.text}`);
    }
  } catch (e) {
    fail("Generate mod (after_tokens)", e.message);
  }

  // Test: after_sentences position
  try {
    const res = await post("/playground/mods/generate", {
      config: {
        injection_string: "ACTUALLY --",
        position: "after_sentences",
        sentence_count: 2,
      },
    });
    if (res.ok && res.json?.code) {
      ok("Generate mod (after_sentences, sentence_count=2)");
    } else {
      fail("Generate mod (after_sentences)", `status ${res.status}: ${res.text}`);
    }
  } catch (e) {
    fail("Generate mod (after_sentences)", e.message);
  }

  // Test: phrase_replace position
  try {
    const res = await post("/playground/mods/generate", {
      config: {
        injection_string: "good",
        position: "phrase_replace",
        detect_phrases: ["bad"],
        replacement_phrases: ["good"],
      },
    });
    if (res.ok && res.json?.code) {
      ok("Generate mod (phrase_replace)");
    } else {
      fail("Generate mod (phrase_replace)", `status ${res.status}: ${res.text}`);
    }
  } catch (e) {
    fail("Generate mod (phrase_replace)", e.message);
  }

  // Test: Qwen-specific position (reasoning_start)
  try {
    const res = await post("/playground/mods/generate", {
      config: {
        injection_string: "Let me reconsider --",
        position: "reasoning_start",
      },
    });
    if (res.ok && res.json?.code) {
      qwenModCode = res.json.code;
      ok("Generate mod (reasoning_start, Qwen-specific)");
    } else {
      fail("Generate mod (reasoning_start)", `status ${res.status}: ${res.text}`);
    }
  } catch (e) {
    fail("Generate mod (reasoning_start)", e.message);
  }

  // Validation error: after_tokens without token_count
  try {
    const res = await post("/playground/mods/generate", {
      config: {
        injection_string: "test",
        position: "after_tokens",
      },
    });
    if (res.status === 400) {
      ok("Validation: after_tokens without token_count -> 400");
    } else {
      fail("Validation: after_tokens without token_count -> 400", `got ${res.status}`);
    }
  } catch (e) {
    fail("Validation: after_tokens without token_count -> 400", e.message);
  }

  // Validation error: phrase_replace without detect_phrases
  try {
    const res = await post("/playground/mods/generate", {
      config: {
        injection_string: "test",
        position: "phrase_replace",
      },
    });
    if (res.status === 400) {
      ok("Validation: phrase_replace without detect_phrases -> 400");
    } else {
      fail("Validation: phrase_replace without detect_phrases -> 400", `got ${res.status}`);
    }
  } catch (e) {
    fail("Validation: phrase_replace without detect_phrases -> 400", e.message);
  }
}

async function testModUpload() {
  section("Mod Upload");

  if (!apiKey || !llamaModCode) {
    skip("Upload mod to Llama 8B", "no api key or mod code from earlier steps");
    skip("Upload mod to Qwen 14B", "no api key or mod code from earlier steps");
    return;
  }

  // Upload to Llama 8B
  try {
    const res = await post(
      "/playground/mods/upload",
      { model: "llama-3.1-8b", code: llamaModCode, mod_name: "playground_mod" },
      { "X-API-Key": apiKey },
    );
    if (res.ok && res.json?.success) {
      ok("Upload mod to Llama 8B", res.json.message);
    } else {
      fail("Upload mod to Llama 8B", `status ${res.status}: ${res.text}`);
    }
  } catch (e) {
    fail("Upload mod to Llama 8B", e.message);
  }

  // Upload to Qwen 14B
  const qwenCode = qwenModCode || llamaModCode;
  try {
    const res = await post(
      "/playground/mods/upload",
      { model: "qwen-14b", code: qwenCode, mod_name: "playground_mod" },
      { "X-API-Key": apiKey },
    );
    if (res.ok && res.json?.success) {
      ok("Upload mod to Qwen 14B", res.json.message);
    } else {
      fail("Upload mod to Qwen 14B", `status ${res.status}: ${res.text}`);
    }
  } catch (e) {
    fail("Upload mod to Qwen 14B", e.message);
  }

  // Error: upload without API key
  try {
    const res = await post("/playground/mods/upload", {
      model: "llama-3.1-8b",
      code: llamaModCode,
      mod_name: "playground_mod",
    });
    if (res.status === 401) {
      ok("Upload without API key -> 401");
    } else {
      fail("Upload without API key -> 401", `got ${res.status}`);
    }
  } catch (e) {
    fail("Upload without API key -> 401", e.message);
  }
}

async function testInference() {
  section("Inference (this may take 30-60s per model as servers cold-start)");

  if (!apiKey) {
    skip("All inference tests", "no api key from earlier steps");
    return;
  }

  const testMessages = [
    { role: "system", content: "You are a helpful assistant. Be concise." },
    { role: "user", content: "What is 2+2? Answer in one sentence." },
  ];

  // Llama 8B: plain inference (no mod)
  try {
    const res = await post(
      "/playground/inference",
      {
        model: "llama-3.1-8b",
        messages: testMessages,
        max_tokens: 64,
        temperature: 0.1,
      },
      { "X-API-Key": apiKey },
    );
    if (!res.ok) {
      fail("Llama 8B inference (no mod)", `status ${res.status}: ${res.text}`);
    } else if (typeof res.json?.text !== "string" || res.json.text.length === 0) {
      fail("Llama 8B inference (no mod) returned text", JSON.stringify(res.json));
    } else {
      llamaInferenceText = res.json.text;
      llamaRequestId = res.json.request_id;
      ok("Llama 8B inference (no mod)", `"${llamaInferenceText.slice(0, 80)}..."`);
      // Verify response shape
      if ("raw_response" in res.json) {
        ok("Llama 8B response has raw_response field");
      } else {
        fail("Llama 8B response has raw_response field", "missing");
      }
    }
  } catch (e) {
    fail("Llama 8B inference (no mod)", e.message);
  }

  // Llama 8B: inference WITH mod
  try {
    const res = await post(
      "/playground/inference",
      {
        model: "llama-3.1-8b",
        messages: testMessages,
        mod_name: "playground_mod",
        max_tokens: 64,
        temperature: 0.1,
      },
      { "X-API-Key": apiKey },
    );
    if (!res.ok) {
      fail("Llama 8B inference (with mod)", `status ${res.status}: ${res.text}`);
    } else if (typeof res.json?.text !== "string" || res.json.text.length === 0) {
      fail("Llama 8B inference (with mod) returned text", JSON.stringify(res.json));
    } else {
      ok("Llama 8B inference (with mod)", `"${res.json.text.slice(0, 80)}..."`);
    }
  } catch (e) {
    fail("Llama 8B inference (with mod)", e.message);
  }

  // Qwen 14B: plain inference (no mod)
  try {
    const res = await post(
      "/playground/inference",
      {
        model: "qwen-14b",
        messages: testMessages,
        max_tokens: 64,
        temperature: 0.1,
      },
      { "X-API-Key": apiKey },
    );
    if (!res.ok) {
      fail("Qwen 14B inference (no mod)", `status ${res.status}: ${res.text}`);
    } else if (typeof res.json?.text !== "string" || res.json.text.length === 0) {
      fail("Qwen 14B inference (no mod) returned text", JSON.stringify(res.json));
    } else {
      qwenInferenceText = res.json.text;
      ok("Qwen 14B inference (no mod)", `"${qwenInferenceText.slice(0, 80)}..."`);
    }
  } catch (e) {
    fail("Qwen 14B inference (no mod)", e.message);
  }

  // Qwen 14B: inference WITH mod
  try {
    const res = await post(
      "/playground/inference",
      {
        model: "qwen-14b",
        messages: testMessages,
        mod_name: "playground_mod",
        max_tokens: 64,
        temperature: 0.1,
      },
      { "X-API-Key": apiKey },
    );
    if (!res.ok) {
      fail("Qwen 14B inference (with mod)", `status ${res.status}: ${res.text}`);
    } else if (typeof res.json?.text !== "string" || res.json.text.length === 0) {
      fail("Qwen 14B inference (with mod) returned text", JSON.stringify(res.json));
    } else {
      ok("Qwen 14B inference (with mod)", `"${res.json.text.slice(0, 80)}..."`);
    }
  } catch (e) {
    fail("Qwen 14B inference (with mod)", e.message);
  }

  // Error: inference without API key
  try {
    const res = await post("/playground/inference", {
      model: "llama-3.1-8b",
      messages: testMessages,
      max_tokens: 32,
    });
    if (res.status === 401) {
      ok("Inference without API key -> 401");
    } else {
      fail("Inference without API key -> 401", `got ${res.status}`);
    }
  } catch (e) {
    fail("Inference without API key -> 401", e.message);
  }

  // Error: inference with unknown model
  try {
    const res = await post(
      "/playground/inference",
      {
        model: "gpt-4-turbo",
        messages: testMessages,
        max_tokens: 32,
      },
      { "X-API-Key": apiKey },
    );
    if (res.status === 400) {
      ok("Inference with unknown model -> 400");
    } else {
      fail("Inference with unknown model -> 400", `got ${res.status}`);
    }
  } catch (e) {
    fail("Inference with unknown model -> 400", e.message);
  }
}

async function testFeatureExtraction() {
  section("SAE Feature Extraction (Llama 8B only)");

  if (!apiKey) {
    skip("All feature extraction tests", "no api key from earlier steps");
    return;
  }

  // We need real token IDs. Use a short known sequence.
  // Llama 3.1 tokenizer: "Hello world" is roughly [9906, 1917] but exact IDs depend on tokenizer.
  // Instead of hardcoding, we'll use small integer token IDs that are valid for any LLM tokenizer.
  // Token IDs 1-20 are always valid (common tokens in any vocabulary).
  const testTokens = [1, 9906, 3186, 338, 263, 1243, 29889]; // approximate "Hello this is a test."

  try {
    const res = await post(
      "/playground/features/extract",
      {
        model: "llama-3.1-8b",
        tokens: testTokens,
        top_k: 5,
        layer: 16,
      },
      { "X-API-Key": apiKey },
    );
    if (!res.ok) {
      fail("Extract features (Llama 8B)", `status ${res.status}: ${res.text}`);
    } else if (!Array.isArray(res.json?.feature_timeline)) {
      fail("Extract features response has feature_timeline array", JSON.stringify(res.json)?.slice(0, 200));
    } else {
      const timeline = res.json.feature_timeline;
      ok("Extract features (Llama 8B)", `${timeline.length} positions returned`);

      // Validate timeline entry shape
      if (timeline.length > 0) {
        const entry = timeline[0];
        const hasPosition = typeof entry.position === "number";
        const hasToken = typeof entry.token === "number";
        const hasTokenStr = typeof entry.token_str === "string";
        const hasTopFeatures = Array.isArray(entry.top_features);
        if (hasPosition && hasToken && hasTokenStr && hasTopFeatures) {
          ok("Feature timeline entry shape: { position, token, token_str, top_features }");
        } else {
          fail("Feature timeline entry shape", JSON.stringify(entry).slice(0, 200));
        }

        // Validate feature activation shape
        if (hasTopFeatures && entry.top_features.length > 0) {
          const feat = entry.top_features[0];
          if (typeof feat.id === "number" && typeof feat.activation === "number") {
            ok("Feature activation shape: { id, activation }", `id=${feat.id} act=${feat.activation.toFixed(4)}`);
          } else {
            fail("Feature activation shape", JSON.stringify(feat));
          }
        }
      }
    }
  } catch (e) {
    fail("Extract features (Llama 8B)", e.message);
  }

  // With injection_positions for comparison data
  try {
    const res = await post(
      "/playground/features/extract",
      {
        model: "llama-3.1-8b",
        tokens: testTokens,
        top_k: 5,
        layer: 16,
        injection_positions: [2],
      },
      { "X-API-Key": apiKey },
    );
    if (res.ok && Array.isArray(res.json?.feature_timeline)) {
      ok("Extract features with injection_positions", `comparisons: ${res.json.comparisons ? "present" : "absent"}`);
    } else {
      fail("Extract features with injection_positions", `status ${res.status}: ${res.text?.slice(0, 200)}`);
    }
  } catch (e) {
    fail("Extract features with injection_positions", e.message);
  }

  // Error: feature extraction on Qwen -> should 400
  try {
    const res = await post(
      "/playground/features/extract",
      {
        model: "qwen-14b",
        tokens: [1, 2, 3],
        top_k: 5,
      },
      { "X-API-Key": apiKey },
    );
    if (res.status === 400) {
      ok("Feature extraction on Qwen -> 400 (unsupported)");
    } else {
      fail("Feature extraction on Qwen -> 400", `got ${res.status}`);
    }
  } catch (e) {
    fail("Feature extraction on Qwen -> 400", e.message);
  }

  // Error: feature extraction without API key -> 401
  try {
    const res = await post("/playground/features/extract", {
      model: "llama-3.1-8b",
      tokens: [1, 2, 3],
    });
    if (res.status === 401) {
      ok("Feature extraction without API key -> 401");
    } else {
      fail("Feature extraction without API key -> 401", `got ${res.status}`);
    }
  } catch (e) {
    fail("Feature extraction without API key -> 401", e.message);
  }
}

async function testFeatureAnalysis() {
  section("SAE Feature Analysis (Claude-powered)");

  if (!apiKey) {
    skip("All feature analysis tests", "no api key from earlier steps");
    return;
  }

  // Build a minimal but valid feature timeline for analysis
  const mockTimeline = [
    {
      position: 0,
      token: 9906,
      token_str: "Hello",
      top_features: [
        { id: 12345, activation: 0.85 },
        { id: 67890, activation: 0.62 },
      ],
    },
    {
      position: 1,
      token: 3186,
      token_str: " world",
      top_features: [
        { id: 11111, activation: 0.91 },
        { id: 22222, activation: 0.45 },
      ],
    },
  ];

  try {
    const res = await post(
      "/playground/features/analyze",
      {
        model: "llama-3.1-8b",
        feature_timeline: mockTimeline,
        context: "Testing the SAE analysis pipeline",
        layer: 16,
      },
      { "X-API-Key": apiKey },
    );
    if (!res.ok) {
      fail("Analyze features (Llama 8B)", `status ${res.status}: ${res.text?.slice(0, 300)}`);
    } else {
      if (typeof res.json?.analysis === "string" && res.json.analysis.length > 0) {
        ok("Analyze features returns analysis text", `${res.json.analysis.length} chars`);
      } else {
        fail("Analyze features returns analysis text", JSON.stringify(res.json)?.slice(0, 200));
      }
      if (Array.isArray(res.json?.top_features)) {
        ok("Analyze features returns top_features array", `${res.json.top_features.length} features`);
        if (res.json.top_features.length > 0) {
          const f = res.json.top_features[0];
          if (typeof f.id === "number" && typeof f.activation === "number" && typeof f.description === "string") {
            ok("Feature with description shape: { id, activation, description }");
          } else {
            fail("Feature with description shape", JSON.stringify(f));
          }
        }
      } else {
        fail("Analyze features returns top_features array", JSON.stringify(res.json)?.slice(0, 200));
      }
    }
  } catch (e) {
    fail("Analyze features (Llama 8B)", e.message);
  }

  // Error: analyze on Qwen -> 400
  try {
    const res = await post(
      "/playground/features/analyze",
      {
        model: "qwen-14b",
        feature_timeline: mockTimeline,
      },
      { "X-API-Key": apiKey },
    );
    if (res.status === 400) {
      ok("Feature analysis on Qwen -> 400 (unsupported)");
    } else {
      fail("Feature analysis on Qwen -> 400", `got ${res.status}`);
    }
  } catch (e) {
    fail("Feature analysis on Qwen -> 400", e.message);
  }

  // Error: analyze without API key -> 401
  try {
    const res = await post("/playground/features/analyze", {
      model: "llama-3.1-8b",
      feature_timeline: mockTimeline,
    });
    if (res.status === 401) {
      ok("Feature analysis without API key -> 401");
    } else {
      fail("Feature analysis without API key -> 401", `got ${res.status}`);
    }
  } catch (e) {
    fail("Feature analysis without API key -> 401", e.message);
  }
}

async function testLogRetrieval() {
  section("Log Retrieval");

  if (!apiKey) {
    skip("Log retrieval tests", "no api key from earlier steps");
    return;
  }

  // List logs with the playground API key (should see our own inference requests)
  try {
    const res = await get("/logs?limit=5", { "X-API-Key": apiKey });
    if (res.ok && Array.isArray(res.json?.logs)) {
      ok("GET /logs returns logs array", `${res.json.logs.length} logs visible`);
    } else if (res.ok) {
      // Might have different shape
      ok("GET /logs returns 200", `response keys: ${Object.keys(res.json || {}).join(", ")}`);
    } else {
      fail("GET /logs returns 200", `status ${res.status}`);
    }
  } catch (e) {
    fail("GET /logs returns 200", e.message);
  }

  // Fetch specific log if we have a request_id from inference
  if (llamaRequestId) {
    try {
      const res = await get(`/logs/${llamaRequestId}`, { "X-API-Key": apiKey });
      if (res.ok) {
        ok("GET /logs/:request_id for Llama inference", `model: ${res.json?.model_id || "unknown"}`);
      } else {
        // Log might not be ingested yet (async), so don't hard-fail
        skip("GET /logs/:request_id for Llama inference", `status ${res.status} (may not be ingested yet)`);
      }
    } catch (e) {
      skip("GET /logs/:request_id for Llama inference", e.message);
    }
  }
}

// ---------------------------------------------------------------------------
// Runner
// ---------------------------------------------------------------------------

async function main() {
  console.log(`${BOLD}Concordance Playground Infrastructure Tests${RESET}`);
  console.log(`Target: ${API_BASE}`);
  console.log(`Time:   ${new Date().toISOString()}`);

  const t0 = Date.now();

  await testHealth();
  await testApiKeyGeneration();
  await testModGeneration();
  await testModUpload();
  await testInference();
  await testFeatureExtraction();
  await testFeatureAnalysis();
  await testLogRetrieval();

  const elapsed = ((Date.now() - t0) / 1000).toFixed(1);

  console.log(`\n${BOLD}========================================${RESET}`);
  console.log(`${GREEN}Passed: ${passed}${RESET}  ${failed ? `${RED}Failed: ${failed}${RESET}` : `Failed: 0`}  ${skipped ? `${YELLOW}Skipped: ${skipped}${RESET}` : `Skipped: 0`}`);
  console.log(`Elapsed: ${elapsed}s`);

  if (failures.length > 0) {
    console.log(`\n${RED}${BOLD}Failures:${RESET}`);
    for (const f of failures) {
      console.log(`  ${RED}x${RESET} ${f.name}: ${f.reason}`);
    }
  }

  console.log(`${BOLD}========================================${RESET}\n`);
  process.exit(failed > 0 ? 1 : 0);
}

main().catch((e) => {
  console.error(`\n${RED}Fatal error: ${e.message}${RESET}`);
  console.error(e.stack);
  process.exit(2);
});
