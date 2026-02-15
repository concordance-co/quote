# Phase 3 Deep Review: Frontend Polish

## Reviewer Context

Phase 3 of `STAGING_ACTIVATIONS_SPEC.md` covers three items:
1. Hide/disable the "Feature Delta Timeline" panel (backend will return 501)
2. Update copy: replace "Token/feature rows from engine activation store" with "Preview rows from SAE timeline"
3. Ensure the activations playground works with the new backend

This review analyzes the existing frontend codebase to identify all changes needed, gaps in the spec, and proposes concrete implementation tasks.

---

## 1. Feature Delta Timeline Panel

### Current State
- **File**: `frontend/src/components/ActivationExplorer.tsx`, lines 413–462
- The panel is always rendered as a `<Card>` in the bottom grid row (alongside "Activation Rows")
- It has:
  - A feature ID number input + search button
  - A loading spinner
  - Renders delta rows when `featureDeltas` state is populated
- The `fetchFeatureDeltas` callback (lines 156–180) calls `getActivationExplorerFeatureDeltas()` which hits `GET /playground/activations/:request_id/feature-deltas`
- **No error handling specific to 501 status** — the generic `handleApiError` in `api.ts` will throw an `ApiError`, which the catch block converts to a generic error string shown in the error banner

### What the Spec Says
- Backend will return `501 Not Implemented` (or a structured error)
- Frontend should "hide/disable" this panel

### Gaps & Decisions Needed
1. **Hide vs disable?** The spec says "hide/disable" but doesn't specify which. Options:
   - **Option A**: Remove the panel entirely from the DOM (cleanest for staging UX)
   - **Option B**: Render the panel with inputs disabled and a "Coming Soon" message
   - **Recommendation**: Option A — fully hide it. Less confusing for users, and the panel is not useful without the endpoint. A simple boolean constant or env flag can bring it back later.

2. **Dead code cleanup**: If hidden, should we also remove the related state (`featureDeltas`, `featureIdInput`, `isLoadingDeltas`) and the `fetchFeatureDeltas` callback?
   - **Recommendation**: Keep the state/callback code commented or guarded by a constant, not deleted. This makes re-enabling trivial when feature-deltas are implemented.
   - Alternative: Use a `const FEATURE_DELTAS_ENABLED = false;` flag to conditionally render and skip the import.

3. **API function cleanup**: `getActivationExplorerFeatureDeltas` in `api.ts` and the `ActivationExplorerFeatureDeltasResponse` type — should these be removed?
   - **Recommendation**: Keep them. They're not harmful and will be needed later. Only remove the runtime call path.

4. **`loadRequestDetails` parallel call**: Currently `loadRequestDetails()` (line 97–117) does NOT call `getActivationExplorerFeatureDeltas` in its `Promise.all`. The feature deltas are only fetched on-demand when the user clicks the search button. So hiding the panel alone is sufficient — no parallel fetch logic needs changing.

### Files Affected
| File | Change |
|------|--------|
| `frontend/src/components/ActivationExplorer.tsx` | Conditionally hide lines 413–462 (the Feature Delta Timeline `<Card>`) |

### Estimated LOC
- ~5 lines (add a flag constant + wrap the Card in a conditional)

---

## 2. Activation Rows Copy Update

### Current State
- **File**: `frontend/src/components/ActivationExplorer.tsx`, line 378
- Current text: `"Token/feature rows from engine activation store."`
- This `<CardDescription>` sits under the "Activation Rows" `<CardTitle>` (line 377)

### What the Spec Says
- Replace with: `"Preview rows from SAE timeline"`

### Gaps & Decisions Needed
1. **Exact copy**: The spec gives an exact replacement string. No ambiguity here.
2. **Other copy to update?** Reviewing all user-visible text in the component:
   - Line 200: `"Activation Explorer (v0)"` — **should this change?** The spec doesn't mention it, but "v0" may be misleading if this is a new backend. Recommend leaving as-is for now.
   - Line 202: `"Run local fullpass with optional inline SAE extraction and inspect activation data."` — **"local fullpass" is inaccurate** now that the backend uses HF inference + SAE service (not engine-local fullpass). The spec doesn't mention this, but it should be updated.
   - Line 130: `"Running activation fullpass..."` — status message during run. Similarly references "fullpass" which is the old engine concept. Should update.
   - Line 306: `"Indexed metadata from backend run index."` — under "Recent Runs". Still accurate.
   - Line 415: `"Feature Delta Timeline"` — will be hidden, so doesn't matter.
   - Line 364: `"Aggregated by request (max activation + hit count)."` — under "Top Features". Still accurate.

### Additional Copy Issues Found (Not in Spec)
| Line | Current Copy | Issue | Suggested Replacement |
|------|-------------|-------|----------------------|
| 202 | "Run local fullpass with optional inline SAE extraction and inspect activation data." | References "local fullpass" — no longer accurate with new HF inference backend | "Run inference with SAE feature extraction and inspect activation data." |
| 130 | "Running activation fullpass..." | References "fullpass" | "Running activation analysis..." |

### Files Affected
| File | Change |
|------|--------|
| `frontend/src/components/ActivationExplorer.tsx` | Update line 378 CardDescription text |
| `frontend/src/components/ActivationExplorer.tsx` | (Recommended) Update lines 130, 202 to remove "fullpass" language |

### Estimated LOC
- 3 lines (1 required change + 2 recommended)

---

## 3. Activations Playground Compatibility with New Backend

### Current API Surface (Frontend → Backend)

| API Function | Endpoint | Used In | Status |
|---|---|---|---|
| `runActivationExplorer()` | `POST /playground/activations/run` | `runModel()` callback | **Compatible** — request shape matches spec. Backend changes are transparent. |
| `listActivationExplorerRuns()` | `GET /playground/activations/runs` | `refreshRuns()` callback | **Compatible** — response shape unchanged. |
| `getActivationExplorerRunSummary()` | `GET /playground/activations/:id/summary` | `loadRequestDetails()` | **Compatible** — response shape unchanged. |
| `getActivationExplorerRows()` | `GET /playground/activations/:id/rows` | `loadRequestDetails()` | **Compatible** — response shape unchanged (rows derived from SAE timeline now). |
| `getActivationExplorerTopFeatures()` | `GET /playground/activations/:id/top-features` | `loadRequestDetails()` | **Compatible** — response shape unchanged. |
| `getActivationExplorerFeatureDeltas()` | `GET /playground/activations/:id/feature-deltas` | `fetchFeatureDeltas()` | **Will return 501** — panel should be hidden (see Section 1). |
| `getActivationExplorerHealth()` | `GET /playground/activations/health` | `refreshRuns()` | **Needs update** — see below. |

### Health Endpoint Compatibility Issue

**Current backend health response** (from `activation_explorer.rs:975–1010`):
```json
{
  "status": "ok" | "degraded",
  "engine_reachable": true/false,
  "index_db_reachable": true/false,
  "last_error": "string" | null
}
```

**Current frontend type** (from `api.ts:1062–1067`):
```typescript
interface ActivationExplorerHealthResponse {
  status: "ok" | "degraded";
  engine_reachable: boolean;
  index_db_reachable: boolean;
  last_error: string | null;
}
```

**Spec says** (Phase 0 / Architecture section):
> `health` should stop checking engine debug endpoints; instead check:
> - PG reachable
> - HF inference service reachable (new)
> - SAE service reachable (optional but recommended)

**Frontend impact**: The health response fields will change. The backend will likely replace `engine_reachable` with something like `hf_inference_reachable` and possibly add `sae_reachable`. The frontend currently only uses `health.status` for the badge display (line 285), so the `status` field is what matters most. However, the TypeScript type needs updating to match whatever the backend returns.

**Gaps:**
1. The spec doesn't define the new health response shape explicitly.
2. The frontend type `ActivationExplorerHealthResponse` references `engine_reachable` which will no longer exist.
3. The frontend only displays `health.status` as a badge, so the actual field name change won't break the UI visually — but TypeScript compilation will fail if the type doesn't match.

**Recommendation**: Update the `ActivationExplorerHealthResponse` type to match the new backend response once Phase 0 is implemented. Since the frontend only uses `health.status`, this is low-risk.

### Request Payload Compatibility

The `ActivationExplorerRunRequest` interface includes fields that may not be relevant in the new backend:
- `collect_activations` — the new backend always collects (no opt-out), but sending `true` is harmless
- `sae_local_path` — was for engine-local SAE model path, irrelevant for new backend. Not sent in current UI code. Safe to leave in the type.
- `temperature`, `top_p`, `top_k` — not exposed in the UI form currently (no inputs for these). The spec mentions them in the API contract. Not a Phase 3 concern, but worth noting for UX improvement.

### Missing: API Auth for Activation Explorer

Looking at `api.ts`, the activation explorer API calls use raw `axios` (not the `api` instance with interceptor). This means:
- `runActivationExplorer()` (line 1073) — uses `axios.post` directly, **no API key header**
- `listActivationExplorerRuns()` (line 1094) — uses `axios.get` directly, **no API key header**
- All activation explorer functions use `axios` directly rather than the `api` instance

This is different from the regular playground APIs which also use `axios` directly but explicitly pass the API key. The activation explorer doesn't include auth headers at all.

**This may be intentional** (activations page is a public route per `App.tsx:635`), but if the backend starts requiring auth, this will need fixing. Not a Phase 3 blocker unless auth is being added.

---

## 4. Additional Findings

### 4a. Grid Layout After Hiding Feature Deltas Panel
- Lines 374–463: The bottom grid uses `lg:grid-cols-2` with "Activation Rows" on the left and "Feature Delta Timeline" on the right
- If Feature Delta Timeline is hidden, "Activation Rows" will span the full width (single item in a 2-col grid takes col 1 only, leaving col 2 empty)
- **Options**:
  - Change to `lg:grid-cols-1` when deltas panel is hidden (Activation Rows takes full width)
  - Or leave as-is (Activation Rows stays left-aligned at ~50% width)
  - **Recommendation**: Make Activation Rows full-width when deltas panel is hidden. Better use of space.

### 4b. Status Message on Run
- Line 130: `"Running activation fullpass..."` — references "fullpass" concept
- Line 147: `Completed run ${response.request_id}` — fine
- Line 150: `"Activation run failed."` — fine

### 4c. Vercel Routing
- `frontend/vercel.json` rewrites `/api/:path*` to the staging Modal backend
- This means all `/playground/activations/*` API calls already route correctly through the Vercel proxy — no changes needed for routing

### 4d. No Feature Flags Infrastructure
- The frontend has no feature flag system. There's no env-based conditional rendering beyond `import.meta.env.DEV` for debug logging.
- For the Feature Delta Timeline panel, a simple `const` flag is sufficient. No need to add a feature flag system.

---

## 5. Proposed Implementation Tasks

### Task 1: Hide Feature Delta Timeline Panel
**Priority**: High (required by spec)
**File**: `frontend/src/components/ActivationExplorer.tsx`
**Changes**:
- Add `const FEATURE_DELTAS_ENABLED = false;` at module level
- Wrap the Feature Delta Timeline `<Card>` (lines 413–462) in `{FEATURE_DELTAS_ENABLED && (...)}`
- Adjust the grid layout: when `!FEATURE_DELTAS_ENABLED`, change the bottom grid from `lg:grid-cols-2` to span full width for Activation Rows
- Optionally: wrap the `fetchFeatureDeltas` related state in the same guard (prevents unnecessary state allocation)

**Estimated LOC**: ~10

### Task 2: Update Activation Rows Copy
**Priority**: High (required by spec)
**File**: `frontend/src/components/ActivationExplorer.tsx`
**Changes**:
- Line 378: Change `"Token/feature rows from engine activation store."` → `"Preview rows from SAE timeline."`

**Estimated LOC**: 1

### Task 3: Update Additional Stale Copy (Recommended)
**Priority**: Medium (not in spec, but references deleted architecture)
**File**: `frontend/src/components/ActivationExplorer.tsx`
**Changes**:
- Line 202: Change `"Run local fullpass with optional inline SAE extraction and inspect activation data."` → `"Run inference with SAE feature extraction and inspect activation data."`
- Line 130: Change `"Running activation fullpass..."` → `"Running activation analysis..."`

**Estimated LOC**: 2

### Task 4: Update Health Response TypeScript Type
**Priority**: Medium (will break TS compilation once backend changes land)
**File**: `frontend/src/lib/api.ts`
**Changes**:
- Update `ActivationExplorerHealthResponse` to match new backend health response (likely replace `engine_reachable` with `hf_inference_reachable` and optionally `sae_reachable`)
- This is blocked on the Phase 0 backend health endpoint changes landing first

**Estimated LOC**: ~5

### Task 5: Remove Unused `sae_local_path` from UI (Optional Cleanup)
**Priority**: Low
**File**: `frontend/src/lib/api.ts`
**Changes**:
- Remove `sae_local_path` from `ActivationExplorerRunRequest` if it's confirmed the new backend ignores it
- Low priority since it's not sent in any current UI code

**Estimated LOC**: 1

---

## 6. Summary

| # | Task | Required? | Est. LOC | Blocked On |
|---|------|-----------|----------|------------|
| 1 | Hide Feature Delta Timeline panel | Yes (spec) | ~10 | None |
| 2 | Update Activation Rows copy | Yes (spec) | 1 | None |
| 3 | Update stale "fullpass" copy | Recommended | 2 | None |
| 4 | Update health response TS type | Yes (eventual) | ~5 | Phase 0 backend changes |
| 5 | Remove `sae_local_path` from request type | No (cleanup) | 1 | Confirmation from backend |

**Total estimated LOC for required changes**: ~13
**Total estimated LOC including recommended**: ~19

### Key Spec Gaps Identified
1. **Hide vs disable** — spec says "hide/disable" but doesn't decide. Recommendation: hide entirely.
2. **Health response shape** — spec says to update health checks but doesn't define the new response JSON schema.
3. **Stale copy** — spec only calls out the Activation Rows copy change, but "local fullpass" copy in the header and status messages is also stale.
4. **Grid layout** — spec doesn't address the visual impact of hiding the deltas panel on the 2-column layout.
