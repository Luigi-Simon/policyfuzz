# Person 5 handoff

Status: public UI and transport implemented; schema custody checkpoint published; submission drafts prepared. Final live acceptance and final recording remain dependent on Person 1's backend and verified evidence.

## Interfaces and completed scope

- Generated OpenAPI aliases are the only server field definitions. Ajv validates public snapshots, serialized defaults, relevant cross-field consistency and safe errors. The generator is pinned and its portable drift check detects missing, untracked and changed output.
- `PolicyFuzzTransport` implements create, GET, contract confirmation/rejection, finding decisions, revision confirmation/rejection and deletion. HTTP is the default; explicit `VITE_DATA_MODE=mock` uses authored synthetic fixtures.
- Public HTTP requests have a 15-second bound. Active stages poll every 1,500 ms after the previous GET settles; confirmations and terminal stages stop. Actions refresh state, 409 conflicts retain their context even if resynchronization fails, and aborted/stale responses cannot restore an old run.
- All four views consume only public data. They show exact cited rules, typed intent, visible traces, review decisions, complete structured operations, all seven acceptance gates, aggregate assertion/effect results and full hashes. Missing projections are labelled unavailable. Draft wording remains unverified.
- The bundled sample submits `sample_id: development-policy`; Person 1 Task 20 must register that ID. The mock revision path accepts the cap finding and rejects the approval-gap finding. Reject-all and unsupported selections end without a revision. This is authored display data, not provider output or an evaluated cached run.
- Generated public models require complete serialized defaults such as `schema_version`; Task 20 should return normal Pydantic model serialization, not sparse handcrafted dictionaries. Contract rejection sends null baseline anchors and empty confirmation collections. Deletion is the declared `200 DeleteRunResponse`; structured 409 errors are followed by GET because the error body has no stage/actions.

## Benchmark custody

- Read `submission/evidence/active-benchmark.json` for the current technical candidate. Its source and schema seals live under `submission/evidence/benchmark-v2/`.
- The original candidate could not represent its semantics in the supported vocabulary. Its original seal remains unchanged; `blind-a2-compatibility.md` records the disposition without exposing contents.
- A fresh custodian authored and sealed a separate candidate with 9 rules, 15 scenarios and 3 candidate defects. Existing A1/A2 tools passed; public metadata received independent review and root hash/link/count checks.
- Public checkpoint `2a1e1194740f014d42bc11cd4fb78ce6fbbc76e7` preserves Person 2's preceding extraction commit. Private bundles were saved separately and were not opened by Person 1 or committed to GitHub.
- **Agent-authored, sealed after development, independent human review pending, headline gold scoring ineligible.** Schema-required gold/session-confirmed flags do not establish human approval or oracle correctness. This checkpoint permits technical integration; it does not approve benchmark performance claims.

## Changed file groups

- `frontend/src/api/`, generated client, public schemas/fixture adapters and mock/HTTP transports.
- `frontend/src/state/`, four `views/`, shared `components/`, App/main, responsive stylesheet, package configuration and focused tests.
- `frontend/README.md` and `frontend/INTEGRATION.md` document the mock quickstart, exact wire contract and upstream projection gaps.
- Public custody metadata under `submission/evidence/`.
- `submission/deck/PolicyFuzz-Pitch-Draft.{pptx,pdf}`, reproducible deck source and outline.
- `submission/video/{script,shot-list,recording-checklist}.md`, `submission/checklist.md`, architecture note and draft metric template.
- `scripts/verify_submission.py` and `submission/tests/test_verify_submission.py`.

The temporary `/v1` adapter and its handwritten engine mapping/behavioral preview have been retired from this frontend. Backend feature implementations, shared contracts and other persons' work were preserved.

## Verification

At the reviewed implementation checkpoint:

- `npm run test:run`: **108 tests passed** across 9 files.
- `npm run build`: TypeScript and Vite production build passed.
- `npm run check:generated`: exact generated-client check passed.
- `backend/.venv/bin/python -m pytest submission/tests/test_verify_submission.py -q`: **47 passed**.
- Ruff check and format check passed for the two submission Python files.
- Draft deck: **9 PPTX slides and 9 PDF pages**; slide rendering/overflow checks completed. The corrected evidence sequence is Gate B report → demo-core-v1 → six-hour freeze → capture → review.
- Script and shot list: **9 segments totalling 280 seconds**. No final video or captions were fabricated.

Tests use public synthetic fixtures and fake HTTP only. No provider was called. The environment emits an existing npm proxy-configuration warning; it did not affect the successful commands. Whole-repository CI/backend acceptance is not claimed by these frontend/submission checks.

## Submission verifier contract

The verifier rejects draft/missing evidence, unresolved claims, inconsistent displayed values, invalid provenance labels, mismatched source hashes, private paths, symlinks, corrupt media and oversized candidate contents. It uses a fixed required-metric registry and documented claim syntax. Person 1 Task 25 must reuse `enumerate_candidate_files` from the verifier for packaging and separately verify the resulting archive. Safe root/nested `.env.example` setup templates are included; actual environment files are excluded. Repeated source basenames such as `AGENTS.md` are valid; final deliverable filenames must be unique.

Current draft verification must return nonzero: final media, frozen metrics, Gate B evidence and independent reviews do not exist. The draft deck's planned cases and pending results must be replaced only with verified captures and source-backed measurements.

## Remaining gates and ownership

1. **Person 1 Task 4 can proceed** using the active technical candidate and current public schemas; freeze the contract and regenerate client types after any approved change.
2. Persons 1–4 finish their backend stages; Person 1 Tasks 19–20 provide the actual coordinator/API. `frontend/INTEGRATION.md` lists missing visible scenario/assertion details, coverage-lift data, regression IDs, engine version and reload history. The UI does not invent them.
3. Complete a real bundled public-HTTP workflow and browser acceptance at 375 px and 1440 px, keyboard-only. The controlled browser rejected localhost with `ERR_BLOCKED_BY_CLIENT`; DOM tests and static CSS checks do not substitute for this visual gate.
4. Keep private benchmark contents sealed until the approved code/prompt/tooling freeze and reveal procedure. Independent human review remains necessary before headline scoring.
5. Save actual Gate B and benchmark evidence, create `demo-core-v1`, wait the required six hours, then capture final screenshots/video and complete the two human reviews.
6. Person 5 finishes the measured deck, MP4 and captions; Person 1 packages, verifies CI and publishes the final submission/tag.

No final Task 24 completion, recorded demo, live-provider acceptance, blind score, human reviewer identity, `demo-core-v1` or `demo-v1` tag is claimed by this handoff.
