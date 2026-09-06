# Person 5 handoff

Status: public UI and transport implemented; the cached FastAPI workflow passes a same-process real-TCP smoke; current cached rehearsal measurements are incorporated into the deck/video sources. Browser-width/keyboard acceptance, Gate B/freeze evidence, final media, and human reviews remain pending.

## Interfaces and completed scope

- Generated OpenAPI aliases are the only server field definitions. Ajv validates public snapshots, serialized defaults, relevant cross-field consistency and safe errors. The generator is pinned and its portable drift check detects missing, untracked and changed output.
- `PolicyFuzzTransport` implements create, GET, contract confirmation/rejection, finding decisions, revision confirmation/rejection and deletion. HTTP is the default; explicit `VITE_DATA_MODE=mock` uses authored synthetic fixtures.
- Public HTTP requests have a 15-second bound. Active stages poll every 1,500 ms after the previous GET settles; confirmations and terminal stages stop. Actions refresh state, 409 conflicts retain their context even if resynchronization fails, and aborted/stale responses cannot restore an old run.
- All four views consume only public data. They show exact cited rules, typed intent, visible traces, review decisions, complete structured operations, all seven acceptance gates, aggregate assertion/effect results and full hashes. Missing projections are labelled unavailable. Draft wording remains unverified.
- The mock revision path accepts the cap finding and rejects the approval-gap finding. Reject-all and unsupported selections end without a revision. This remains authored display data, not provider output or the evaluated cached run.
- The backend now registers `development-policy`. In cached mode, the public API loads `samples/cached-demo/run-record.json` as a completed run with deletion as its only action. A same-process real-TCP test proves create, GET, completed comparison, accepted patch, `200` deletion, and subsequent `404`; no provider is configured or called.
- Current public cached rehearsal evidence is synthetic and blind-scoring-ineligible: 10 scenarios, 3 baseline findings to 0 remaining, 12 inconclusive assertions to 12 passing, all seven acceptance gates true, 3 authored finding decisions, a 3-operation revision, 4 scripted model responses, 0 targeted cycles, and 0 actual provider calls. These counts are rehearsal evidence, not frozen headline metrics.
- The regenerated rehearsal cache is stable at suite `da14acf2f24997f73cca5c4f786e150ba3f02eadd46ef6a6cf19aa576b49af8c`, engine `1.0.0` / `a8f373b2922f6c5d7f29a6064bde8f0379d727cb4bfea320c9fbb45f748afe42`, and run-manifest `c9e12997100bb91f5d568630db8bc4d328fef1c134c1fc6a3c4c95d7dee94b8a`. Public source byte hashes are recorded in `submission/evidence/demo-run.json`. Three semantic replays passed with execution hash `bab4805986a8d06b3bf80e923018d6f23091885880a21a8b255258189fb2310a`; that replay anchor still needs a checked-in Gate B source before it becomes a final claim.
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
- `submission/video/{script,shot-list,recording-checklist}.md`, draft SRT plus its tested generator, `submission/checklist.md`, architecture note, current rehearsal summary and draft metric template.
- `submission/evidence/browser-rehearsal.md` records the unavailable browser capability and explicitly contains no visual acceptance claim.
- `scripts/verify_submission.py` and `submission/tests/test_verify_submission.py`.

The temporary `/v1` adapter and its handwritten engine mapping/behavioral preview have been retired from this frontend. Backend feature implementations, shared contracts and other persons' work were preserved.

## Verification

At the current rehearsal checkpoint:

- `npm run test:run`: **108 tests passed** across 9 files.
- `npm run build`: TypeScript and Vite production build passed.
- `npm run check:generated`: exact generated-client check passed.
- `backend/.venv/bin/python -m pytest backend/tests/integration/test_http_smoke.py -q`: **1 passed**, using real TCP and the public cached API without a provider.
- `backend/.venv/bin/python -m pytest submission/tests/test_verify_submission.py -q`: **47 passed**.
- `node --test submission/video/build-captions.test.mjs`: **2 passed**; `PolicyFuzz-Demo-Draft.srt` ends at 4:40 and contains only narration, not dependency tokens.
- Ruff check and format check passed for the two submission Python files.
- Draft deck: **9 PPTX slides and 9 PDF pages**; all nine rendered slides were inspected and the overflow test passed. The deck labels its values as a current cached synthetic rehearsal and preserves the Gate B → `demo-core-v1` → six-hour freeze → capture → two-human-review sequence.
- Script and shot list: **9 segments totalling 280 seconds**. The stable cache refresh changed narrated baseline predicate coverage to 23/26 and revised coverage to 25/28; the regenerated draft SRT reflects it. The deck does not display those branch counts, so its files did not require a rebuild. No final MP4 or final captions were fabricated.

Tests use public synthetic fixtures, fake HTTP, or the recorded cached API only. No provider was called. The environment emits an existing npm proxy-configuration warning; it did not affect the successful commands. Whole-repository Gate B/CI acceptance is not claimed by these frontend/submission checks.

## Browser rehearsal limitation

- The documented cloud Chrome session was available, but its runtime could not start workspace processes and did not share the workspace localhost namespace.
- The local runtime had Playwright JavaScript but no browser executable. A scratch install failed on its shared-directory lock; an isolated `/tmp` install repeatedly received an invalid zero-byte archive from the mirror.
- Therefore no page loaded, no 375 px or 1440 px layout was observed, no keyboard-only workflow was executed, and no screenshot was captured. `submission/evidence/browser-rehearsal.md` is the exact next-environment packet. Automated HTTP/component tests do not replace this gate.

## Submission verifier contract

The verifier rejects draft/missing evidence, unresolved claims, inconsistent displayed values, invalid provenance labels, mismatched source hashes, private paths, symlinks, corrupt media and oversized candidate contents. It uses a fixed required-metric registry and documented claim syntax. Person 1 Task 25 must reuse `enumerate_candidate_files` from the verifier for packaging and separately verify the resulting archive. Safe root/nested `.env.example` setup templates are included; actual environment files are excluded. Repeated source basenames such as `AGENTS.md` are valid; final deliverable filenames must be unique.

Current draft verification must return nonzero: final media, frozen metrics, Gate B evidence and independent reviews do not exist. The draft deck's current cached rehearsal values must be refreshed only from the regenerated frozen sources, and frozen UI claims still require verified captures.

## Remaining gates and ownership

1. Keep generated client types synchronized with the public contract. `frontend/INTEGRATION.md` lists the remaining optional projections: individual assertion detail, a dedicated adaptation-cycle/lift field, fixed/regressed IDs, engine version, and completed-run rule/proposal history. The UI does not invent them.
2. Complete automated browser acceptance at 375 px and 1440 px, keyboard-only, in a browser that shares the FastAPI/Vite network namespace. Label any pre-freeze capture as rehearsal.
3. Do not relabel a post-run gold-assisted assessment as first-run discovery recall. That headline remains unmeasured until a separate valid reconciliation exists; the active human-approval gate remains pending.
4. Keep private benchmark contents sealed until the approved code/prompt/tooling freeze and reveal procedure. Independent human review remains necessary before headline scoring.
5. Save actual Gate B and benchmark evidence, create `demo-core-v1`, wait the required six hours, then capture final screenshots/video and complete the two human reviews.
6. Person 5 uses the now-refreshed stable rehearsal anchors, then finishes frozen browser capture, canonical verified metrics, final MP4/captions and final deck. Recompute the rehearsal anchors only after an application-affecting change. Person 1 packages, verifies CI and publishes the final submission/tag.

No final Task 24 completion, recorded demo, live-provider acceptance, blind score, human reviewer identity, `demo-core-v1` or `demo-v1` tag is claimed by this handoff.
