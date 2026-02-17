# Frontend Architecture

This document describes the frontend structure, key user flows, API contracts, and where core behavior is implemented.

## 1. Role in the System

The frontend is a React + TypeScript SPA that provides:

- authenticated log exploration
- real-time log feed updates via WebSocket
- deep trace/log/tokens/metrics inspection per request
- public read-only share pages
- interactive Playground for mod/inference experiments
- Activation Explorer UI for SAE run inspection

Entry point:

- `frontend/src/main.tsx:7` mounts the app and Vercel analytics.

## 2. App Composition and Routing

Main route composition is in `frontend/src/App.tsx:625`.

Public routes (no auth gate):

- `/playground` (`frontend/src/App.tsx:634`)
- `/activations` (`frontend/src/App.tsx:635`)
- legacy redirect: `/playground/activations` -> `/activations` (`frontend/src/App.tsx:637-638`)
- `/share/:publicToken` (`frontend/src/App.tsx:641`)
- `/share/:collectionToken/request/:requestId` (`frontend/src/App.tsx:645`)
- `/share/request/:publicToken` (`frontend/src/App.tsx:649`)

Authenticated app shell is catch-all `/*` via `AppContent` (`frontend/src/App.tsx:653`).

## 3. Authentication Model

Auth provider: `frontend/src/lib/auth.tsx:62`.

Behavior:

- stores key in `localStorage` under `concordance_api_key` (`frontend/src/lib/auth.tsx:14`)
- validates with backend `/auth/validate` (`frontend/src/lib/auth.tsx:76`)
- restores persisted session at startup (`frontend/src/lib/auth.tsx:100-132`)
- exposes `login/logout` context helpers

API key is attached to requests via axios interceptors in:

- `frontend/src/lib/auth.tsx:220`
- `frontend/src/lib/api.ts:20-25`

## 4. API Client and Service Wrappers

Shared axios client: `frontend/src/lib/api.ts:12`.

Core log APIs:

- list logs: `fetchLogs` (`frontend/src/lib/api.ts:64`)
- log detail: `fetchLogDetail` (`frontend/src/lib/api.ts:106`)
- public share read APIs:
  - `getPublicCollection` (`frontend/src/lib/api.ts:636`)
  - `getPublicRequest` (`frontend/src/lib/api.ts:689`)
  - `getRequestViaCollection` (`frontend/src/lib/api.ts:708`)

Playground APIs:

- key generation: `generatePlaygroundKey` (`frontend/src/lib/api.ts:824`)
- generate mod code: `generateModCode` (`frontend/src/lib/api.ts:841`)
- upload mod: `uploadMod` (`frontend/src/lib/api.ts:858`)
- run inference: `runPlaygroundInference` (`frontend/src/lib/api.ts:887`)
- feature extraction/analysis: `extractFeatures` (`frontend/src/lib/api.ts:922`), `analyzeFeatures` (`frontend/src/lib/api.ts:956`)

Activation Explorer APIs:

- run: `runActivationExplorer` (`frontend/src/lib/api.ts:1070`)
- list runs: `listActivationExplorerRuns` (`frontend/src/lib/api.ts:1087`)
- summary: `getActivationExplorerRunSummary` (`frontend/src/lib/api.ts:1105`)
- rows: `getActivationExplorerRows` (`frontend/src/lib/api.ts:1118`)
- top features: `getActivationExplorerTopFeatures` (`frontend/src/lib/api.ts:1159`)
- health: `getActivationExplorerHealth` (`frontend/src/lib/api.ts:1177`)

## 5. Real-Time Log Feed

WebSocket hook: `frontend/src/hooks/useLogStream.ts:44`.

Key behavior:

- WS URL base from `VITE_WS_URL` (`frontend/src/hooks/useLogStream.ts:11`)
- connects using `?api_key=...` query (`frontend/src/hooks/useLogStream.ts:103`)
- handles `new_log` and `lagged` message types (`frontend/src/hooks/useLogStream.ts:166-186`)
- reconnection with exponential backoff up to 6 attempts (`frontend/src/hooks/useLogStream.ts:12`, `137-153`)

## 6. Logs List Flow

Component: `frontend/src/components/LogsList.tsx:100`.

Data flow:

1. fetch paginated summaries (`frontend/src/components/LogsList.tsx:295-320`)
2. subscribe to live stream via `useLogStream` (`frontend/src/components/LogsList.tsx:155`)
3. prepend incoming logs when unfiltered (`frontend/src/components/LogsList.tsx:133-152`)
4. support load-more pagination (`frontend/src/components/LogsList.tsx:335-343`)

State handled in component includes:

- selection/multi-select
- favorites and favorites collection behavior
- collection add/remove workflows
- client-side filters/search

## 7. Log Detail + Trace Inspection

Detail container: `frontend/src/components/LogDetail.tsx:108`.

URL-driven navigation state:

- tab from `?tab=` (`frontend/src/components/LogDetail.tsx:150-156`)
- selected step from `?step=` (`frontend/src/components/LogDetail.tsx:151-157`)

It loads request detail via `fetchLogDetail` (`frontend/src/components/LogDetail.tsx:315`) and renders tabbed views, including `TraceTree` (`frontend/src/components/LogDetail.tsx:651-658`).

### 7.1 TraceTree Rendering

Trace renderer: `frontend/src/components/TraceTree/TraceTree.tsx:14`.

How data is built:

- normalizes and sorts events by `sequence_order` (`frontend/src/components/TraceTree/TraceTree.tsx:53-56`)
- attaches matching mod calls/logs/actions (`frontend/src/components/TraceTree/TraceTree.tsx:60-74`)
- maps step -> first entry for jump-to-step behavior (`frontend/src/components/TraceTree/TraceTree.tsx:98-106`)

Performance strategy:

- virtualized rows with `@tanstack/react-virtual` (`frontend/src/components/TraceTree/TraceTree.tsx:122`)
- dynamic row height estimation based on expansion state (`frontend/src/components/TraceTree/TraceTree.tsx:125-155`)

## 8. Playground Flow

Component: `frontend/src/components/Playground.tsx`.

### 8.1 Session Key Bootstrapping

On mount, it ensures a persistent playground key:

- restore from local storage or create via backend (`frontend/src/components/Playground.tsx:642-663`)
- syncs key with main auth key storage for broader app usage (`frontend/src/components/Playground.tsx:651-662`)

### 8.2 Run Pipeline

`handleRun` (`frontend/src/components/Playground.tsx:871`) runs:

1. optionally generate mod code (`frontend/src/components/Playground.tsx:904`)
2. optionally upload mod (`frontend/src/components/Playground.tsx:922`)
3. run inference (`frontend/src/components/Playground.tsx:934`)
4. poll logs + fetch detail to show full trace (`frontend/src/components/Playground.tsx:950-975`)

### 8.3 SAE Analysis in Playground

- extract features (`frontend/src/components/Playground.tsx:1036`, API wrapper at `frontend/src/lib/api.ts:922`)
- analyze features (`frontend/src/components/Playground.tsx:1072`, API wrapper at `frontend/src/lib/api.ts:956`)
- display panel and timeline in the lower results area (`frontend/src/components/Playground.tsx:1863+`)

### 8.4 Runtime Mapping (MAX Path)

`/playground` is wired to the MAX OpenAI-compatible engine path:

- frontend run call: `runPlaygroundInference` (`frontend/src/components/Playground.tsx:934`)
- API route used: `POST /playground/inference` (`frontend/src/lib/api.ts:898`)
- backend handler: `run_inference` (`backend/src/handlers/playground.rs:1080`)
- backend target call: `POST {model_endpoint}/v1/chat/completions` (`backend/src/handlers/playground.rs:1123`)
- model endpoint selection comes from `PLAYGROUND_QWEN_14B_URL` / `PLAYGROUND_LLAMA_8B_URL` (`backend/src/handlers/playground.rs:59-70`)

SAE in this page is post-hoc sidecar style (separate endpoints):

- `POST /playground/extract-features` -> SAE server `/extract_features` (`backend/src/handlers/playground.rs:1283`, `backend/src/handlers/playground.rs:1321`)
- `POST /playground/analyze-features` -> SAE server `/analyze_features` (`backend/src/handlers/playground.rs:1424`, `backend/src/handlers/playground.rs:1473`)

## 9. Activation Explorer UI

Component: `frontend/src/components/ActivationExplorer.tsx:59`.

Core flow:

- refresh health + recent runs (`frontend/src/components/ActivationExplorer.tsx:82-96`)
- run activation request (`frontend/src/components/ActivationExplorer.tsx:124-155`)
- load details (summary, rows, top features) for selected request (`frontend/src/components/ActivationExplorer.tsx:98-118`)

### 9.1 Runtime Mapping (HF Path)

`/activations` uses the HF activation runtime path:

- frontend run call: `runActivationExplorer` (`frontend/src/components/ActivationExplorer.tsx:135`)
- API route used: `POST /playground/activations/run` (`frontend/src/lib/api.ts:1075`)
- backend handler: `run_activation` (`backend/src/handlers/activation_explorer.rs:393`)
- backend target call: `POST {PLAYGROUND_ACTIVATIONS_HF_URL}/hf/generate` (`backend/src/handlers/activation_explorer.rs:471-483`)

Unlike `/playground`, this path requests inline SAE in the HF call payload (`inline_sae`, `sae_id`, `sae_layer`, `sae_top_k`) (`backend/src/handlers/activation_explorer.rs:491-500`).

Feature deltas UI is compiled but disabled:

- `FEATURE_DELTAS_ENABLED = false` (`frontend/src/components/ActivationExplorer.tsx:24`)
- corresponding panel is conditionally hidden (`frontend/src/components/ActivationExplorer.tsx:414`)

## 10. Data Contract Notes

Activation health payload is backward-compatible:

- backend now returns both `sae_reachable` and `sae_service_reachable` (`backend/src/handlers/activation_explorer.rs:1224+`)
- frontend type accepts both fields (`frontend/src/lib/api.ts:1062+`)

## 11. Environment and Runtime

Frontend environment file (`frontend/.env.example`) currently includes:

- `VITE_WS_URL`
- `BACKEND_URL`

The app code resolves API base URL from `VITE_API_URL` with fallback `/api` (`frontend/src/lib/api.ts:4`, `frontend/src/lib/auth.tsx:11`).

## 12. Local Usage

```bash
cd frontend
npm install
npm run dev
```

Useful scripts:

- type/lint: `npm run lint`
- prod build: `npm run build`
- preview: `npm run preview`
