# PolicyFuzz v2 first-run implementation plan

> Execute the approved first milestone. Design: ../specs/2026-09-10-policyfuzz-v2-first-run-design.md.

## Global constraints

- Exactly four product roles: Orchestrator Agent, Metric Agent, Sandbox Agent, Judge Agent.
- Preserve v1 runtime, APIs, generated schemas, archived fixtures and hashes.
- Preserve `backend/app/v2/sandbox/**`, `backend/tests/v2/sandbox/**`, and the existing shared Sandbox contracts and generated `contracts/v2/**` files.
- No live provider calls; all fixture results must identify themselves as fixture.
- Public output excludes original records, policy descriptions and personality seeds.
- Work on `p1/feat-v2-core`; draft PR targets `p1/feat-policyfuzz-v2`.

### Task 1: Standalone v2 fixture run API

Own ONLY new `backend/app/v2/run_models.py`, `orchestrator.py`, `main.py`,
`export_api.py`, `backend/tests/v2/test_run_api.py`, and `contracts/v2-app/**`.
Read root and v2 AGENTS, the existing contracts/fixtures/protocol, and the design.
Do not edit frontend, shared contract files, friend's paths, docs or dependencies.

Implement synchronous/stateless `POST /api/v2/runs` (200) and
`GET /api/v2/health` in standalone `app.v2.main:app`. Do not modify v1 main.
Body model `CreateRunRequest` contains `policy: RunPolicyInput` and
`fixture_name: Literal['completed','partial_translation_unavailable']='completed'`.
`RunPolicyInput` extends/reuses canonical PolicyInput but accepts only the four
required fields: title, description, agent_seed, agent_count. Enforce title max200,
description max50000, seed max2000, nonblank strings and strict integer count1–100.
Reject non-English Han script in title with a safe input error, and reject nonempty
supporting_documents (out of scope), without modifying the shared contract.

`Orchestrator` accepts a factory returning `SandboxService` for the chosen fixture;
default factory uses `FixtureSandboxService`. Build new UUID run/request IDs,
version `1`, exact description/hash and personality seed/count, empty context and
scenario setups, test_budget8. Await the service with bounded timeout (default30s,
injectable for tests). Always validate_sandbox_result(request,result), reject any
non-fixture execution mode, then apply public_sandbox_result.

Return `PublicSandboxResult` typed model with explicit allowed fields matching
public_sandbox_result, extra forbidden, NO original_records. Reuse public nested
types from canonical contracts. Keep status completed/partial/failed/cancelled.
Safe errors: 422 invalid input, 502 invalid/failed adapter execution, 504 timeout;
fixed `{"detail":"..."}` English messages, never exception or request details.
No provider calls, persistence, logs of policy text or CORS wildcard. Vite proxy
is same-origin so CORS is not required. No fake progress or scoring.

`python -m app.v2.export_api` writes `contracts/v2-app/openapi.json` and
`contracts/v2-app/public-sandbox-result.schema.json`. Support `--check` to compare
without writing, deterministic output. Existing v2 export namespace stays intact.

Write focused failing tests first; exercise complete/partial counts (including1
and100), exact preservation/hash of whitespace in description, IDs/fingerprint,
original-record exclusion and schema exclusion, blank/invalid/oversize inputs,
foreign IDs/fingerprint/wrong mode/tampered display fields, generic exception and
timeout. Test via injected fakes, never live. Run foundation check as regression.
Dependencies are installed at /tmp/policyfuzz-m1-deps; use
PYTHONPATH=/tmp/policyfuzz-m1-deps:backend from repo root.
Run local ruff format/check on owned Python files. Commit only owned files.

### Task 2: V2 form and public evidence

Root owns `frontend/src/v2/**`, v2 frontend tests and generated types/check script;
minimal main.tsx route selection and vite proxy changes, frontend ownership scope
exception, root v2 launch script/package command, CI checks and docs.
Generate types from Task1 OpenAPI. Validate response schema with AJV2020, reject
extra backend data and unexpected modes, safe generic error mapping.
Build labelled form/evidence as specified in design, and focused failing tests
before implementation. Preserve all existing v1 scripts and behavior.

### Task 3: Verification, review and publish

Run backend tests/foundation/schema checks, frontend tests/typecheck/build and
generated drift checks. Browser-test complete and partial runs with actual API;
check narrow and desktop layouts. Review actual diff, fix material findings,
verify v1/shared/friend files unchanged. Record exact commands/results in v2
handoff documentation. Push core branch without force, open draft core→integration
PR. Do not merge or alter main/integration/friend branches.
