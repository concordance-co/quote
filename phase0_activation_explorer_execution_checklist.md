# Phase 0 Activation Explorer Execution Checklist

This checklist operationalizes:
1. `/Users/marshallvyletel/repos/concordance/quote/phase0_activation_explorer_spec.md`
2. Local-first backend-indexed explorer delivery.

## 1. Milestone Plan

### M0: Contract Freeze

1. Confirm endpoint contracts and error codes (Sections 14-15 in spec).
2. Lock backend index schema fields.
3. Lock frontend panel layout and flow-view scope.
4. Freeze non-goals for v0.

Exit criteria:
1. Spec approved with no blocking open questions.

### M1: Backend API + Index

1. Add migration: `activation_run_index`.
2. Add backend module for engine client (timeouts + error mapping).
3. Implement routes:
   1. `POST /playground/activations/run`
   2. `GET /playground/activations/runs`
   3. `GET /playground/activations/:request_id/summary`
   4. `GET /playground/activations/:request_id/rows`
   5. `GET /playground/activations/:request_id/feature-deltas`
   6. `GET /playground/activations/:request_id/top-features`
   7. `GET /playground/activations/health`
4. Enforce query limits and parameter validation.
5. Add integration tests for all routes.

Exit criteria:
1. All backend route tests pass.
2. `run` writes/updates index row on success and error.
3. `runs` pagination deterministic.

### M2: Frontend Explorer

1. Add route: `/playground/activations`.
2. Build sections:
   1. Run panel
   2. Output/summary panel
   3. Activation rows table
   4. Feature timeline chart
   5. Compare runs panel
3. Wire data fetching to backend APIs only.
4. Add loading/error/empty states for each panel.
5. Add frontend tests for run -> inspect -> compare flow.

Exit criteria:
1. One successful run can be executed and inspected end-to-end from UI.

### M3: Flow View Demo Surface

1. Add "Flow View" tab to explorer.
2. Implement replay timeline controls (play/pause, step, speed).
3. Implement synchronized lanes:
   1. token lane
   2. feature lane
   3. optional intervention lane
4. Add click-through interactions from token/feature to details.
5. Polish visual style for partner demos.

Exit criteria:
1. Flow View can replay a real run smoothly and is presentation-ready.

### M4: Stabilization + Demo Script

1. Add local startup guide for engine/backend/frontend.
2. Add "5-minute demo" runbook for partner call usage.
3. Run full verification matrix.
4. Address regressions and freeze.

Exit criteria:
1. All verification checks passing.
2. Team can demo from a fresh local boot.

## 2. Ticket Backlog

## Backend

1. `BE-001`: Add `activation_run_index` migration.
2. `BE-002`: Implement engine explorer client wrapper with timeout + retries.
3. `BE-003`: Implement `POST /playground/activations/run`.
4. `BE-004`: Implement `GET /playground/activations/runs` with cursor pagination.
5. `BE-005`: Implement `GET /playground/activations/:request_id/summary`.
6. `BE-006`: Implement `GET /playground/activations/:request_id/rows`.
7. `BE-007`: Implement `GET /playground/activations/:request_id/feature-deltas`.
8. `BE-008`: Implement `GET /playground/activations/:request_id/top-features`.
9. `BE-009`: Implement `GET /playground/activations/health`.
10. `BE-010`: Add route-level tests and error-code mapping tests.

## Frontend

1. `FE-001`: Add `/playground/activations` route shell.
2. `FE-002`: Build Run panel form + validation.
3. `FE-003`: Build Output/Summary panel.
4. `FE-004`: Build Activation rows table with filtering.
5. `FE-005`: Build Feature timeline panel.
6. `FE-006`: Build Compare panel.
7. `FE-007`: Build Flow View tab and playback controls.
8. `FE-008`: Add component/integration tests for explorer flows.

## Engine (minimal contract support only)

1. `ENG-001`: Confirm stable run endpoint contract for backend.
2. `ENG-002`: Confirm stable feature-deltas query contract.
3. `ENG-003`: Add any missing small query endpoints if backend requires them.
4. `ENG-004`: Keep debug logging readable for local integration troubleshooting.

## Docs and DX

1. `DOC-001`: Add local startup instructions for three services.
2. `DOC-002`: Add partner demo script and fallback scenarios.
3. `DOC-003`: Document known limits for v0.

## 3. Dependency Order

1. `BE-001` before `BE-003/BE-004/BE-005`.
2. `BE-002` before all backend proxy routes.
3. `BE-003..BE-009` before `FE-002..FE-007`.
4. `FE-001` before all frontend feature tickets.
5. `ENG-001/ENG-002` before backend contract hardening.
6. `DOC-001` after M2 baseline works.

## 4. QA Gate Checklist

### Backend gate
1. Route tests pass.
2. Pagination tests pass.
3. Proxy failure mapping tests pass.

### Frontend gate
1. Explorer flow test pass.
2. Timeline fetch/render tests pass.
3. Flow view playback tests pass.

### Local E2E gate
1. Engine starts and responds.
2. Backend starts and can index runs.
3. Frontend run executes successfully.
4. Run appears in indexed run list.
5. Feature timeline and compare panel render correctly.

## 5. Demo Readiness Checklist

1. Preload at least two run examples for comparison.
2. Confirm one run contains meaningful feature spikes.
3. Keep flow-view replay under 60 seconds for live demos.
4. Have backup model config if primary model load is slow.
5. Have fallback screenshots/video if live run fails.

## 6. Cut Criteria (If Timeline Tightens)

Priority cut order:
1. Keep run + rows + feature-deltas + index list.
2. Keep basic compare summary.
3. Cut advanced flow-view polish last (never cut basic flow-view itself).

Non-negotiable for Phase 0:
1. Backend indexing.
2. Local no-auth operation.
3. Explorer can run and inspect real activation data.
