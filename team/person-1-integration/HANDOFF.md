# Person 1 integration handoff

Status: Application implementation and offline verification complete; final benchmark/media release gates pending.

## Current application handoff

Person 1 now wires the real policy compiler, per-run scenario planner, deterministic evaluator,
finding analyzer, structured revision applier and regression analyzer through FastAPI.
The published version `1.0` domain models, protocol signatures and HTTP contracts remain the
shared interface. Read the root README for the cached demonstration and live-server setup.

- `app.container.build_container` owns configuration, provider lifecycle, specialist injection,
  per-run planner scope and background jobs. Use `await container.execute(run_id, work)` for
  direct coordinator stage calls so planner state stays scoped to the run.
- `app.api` implements create/read, contract confirmation, finding review, revision confirmation,
  deletion and health. Stale actions fail without mutating a run; deletion, expiry and shutdown
  cancel owned jobs and discard in-memory state.
- `scripts/offline_smoke.py` runs actual stages with explicit scripted model responses and
  authored demo confirmations. `--record` writes the labelled development cache. The production
  cached API replays validated evidence; it never calls a provider.
- `scripts/replay_check.py` reruns baseline and revision three times and verifies current engine
  source commitments. `scripts/validate_contracts.py` checks all 111 schemas, OpenAPI and fixture
  bytes without replacing the canonical files. `scripts/verify_benchmarks.py` independently
  checks public synthetic development/control labels.
- `scripts/record_blind_run.py` requires a clean annotated tag and hash-bound human approval,
  reserves a single attempt before provider calls, pauses for explicit human commands and
  preserves the raw run plus provenance. It cannot approve labels or conceal a failed attempt.
- `scripts/run_gate_b.py` verifies a clean commit, human evidence and fixed verification commands.
  `scripts/package_submission.py` checks final media, tags, secret exclusions and archive integrity.
  CI runs the application checks on ordinary pushes and final submission checks on demo tags.

The current demonstration is synthetic and scripted. It is not a live-provider quality result.
Independent human benchmark approval, the sealed blind attempt and manual reviews, browser
acceptance, the six-hour release freeze and final reviewed media remain separate gates.
Strict gold-suite execution scoring does not establish first-run discovery recall when the normal
workflow generated different scenarios; a post-run gold-assisted assessment must stay labelled
and cannot satisfy that headline gate. The old plan's direct blind-scoring command therefore does
not by itself finish benchmark acceptance.

The task-by-task release status is recorded in `docs/implementation-status.md`.
Current checks: 1,470 backend tests, 108 frontend tests, production build, 111-schema drift,
three-run replay and independent public benchmark verification all pass. See the explicitly
non-Gate-B `team/person-1-integration/evidence/demo-readiness-verification.json`. Historical
verification below remains dated evidence, not the current complete-suite test count.

## Demo-readiness follow-up — 2026-09-06

The latest Person 2 validation work at `5f77c44` is preserved. Application change
`584b92415c5f0cddafb458b94d8d11b9090685bb` matches the locally reviewed tree
`429160ebf516d64caec97adf3a84d5e512703180`.

- Contract/finding HTTP confirmations now validate and persist their decision before
  submitting an owned continuation through `AppContainer.submit`. They return the active
  `RunView` promptly; clients poll for the next confirmation or terminal state.
- Optional internal `schedule` callbacks on `RunCoordinator.confirm_contract` and
  `select_findings` preserve await-to-completion semantics for direct callers by default.
  Frozen HTTP schemas/status codes and specialist protocols are unchanged.
- Event-gated tests reproduce the former blocking requests and cover duplicate/stale
  commands, request cancellation, scoped planner ownership, safe failure, deletion,
  expiry and shutdown. The direct offline flow and replay still pass.
- `scripts/check_setup.py --mode mock|cached|live` checks local prerequisites and
  configuration without contacting a provider or loading `.env`. It returns exit 0/1;
  it does not verify key validity, model access, account quota, ports or browser behavior.
- `docs/demo-day-guide.md` supplies Windows commands, safe local key entry, a labelled
  fallback, a rehearsal sequence, judging questions and the remaining evidence checklist.
- CI adds real Windows setup checks alongside the Linux application job. The actual
  result is recorded in the linked verification file; it is not a Windows browser test.

Changed application paths: `backend/app/{api/routes.py,container.py,workflow/coordinator.py}`.
Corresponding API tests, `backend/tests/integration/test_check_setup.py`, the setup script,
root README and CI, rehearsal guide and this handoff are the complete follow-up surface.
No live provider, browser acceptance, blind eligibility, human review or final media
approval is claimed by this preparation work. Earlier evidence is retained in
`implementation-verification.json`.

## Historical Task 19 handoff

Status: Task 19 workflow implementation and offline verification are complete.
Task 4 remains frozen as version `1.0` and published at `323f06a`.

## Task 19 interfaces

Read `contracts/task19-workflow.md` for the coordinator constructor, state and
retention rules, hash mapping, confirmation semantics, and specialist boundaries.

- `app.workflow.coordinator.RunCoordinator` connects the frozen stage protocols.
- `app.workflow.store.RunStore` provides per-run compare-and-swap mutations and
  monotonic expiry; `app.workflow.types.StoredRun` is a private storage type.
- `app.workflow.state_machine` owns legal transitions and allowed actions.
- `app.workflow.views.to_run_view` constructs the existing public view explicitly.
- `app.workflow.fake_stages` supplies scripted protocol fakes for offline tests.
- `app.workflow.validation` checks stage evidence and cached replay anchors.

No HTTP or shared schema migration is introduced by Task 19. In particular,
the public command bodies retain their existing baseline policy hash, finding
decisions, and proposal ID. Private store versions are not public response fields.

## Task 19 verification

Final full-suite verification at implementation commit `7beac49`:

- `.venv/bin/python -m pytest -q` from `backend`: **1,125 passed**.
- Final stage-entry wording regression suite: **535 passed**; its five changed
  Python files passed Ruff check and format check.
- Earlier store/state focused tests: **534 passed**; scripted fakes: **18 passed**.
- Coordinator, public view, and four integration-flow files: **57 passed**.
- Ruff check and format check: **20 owned Python files passed**.
- Schema/OpenAPI and canonical completed-fixture drift checks: **passed**.
- `npm run check:generated` from `frontend`: **passed**; existing npm environment
  warning about `http-proxy` remains outside the changed source.
- All **129 Task 4 frozen source/artifact hashes** remain unchanged.
- Domain/core, specialist features/tests, frontend, samples, submission, and
  backend dependencies are unchanged by this task.

Store/state/fake and coordinator/view independent reviews are approved. All
three orchestration findings were fixed and passed scoped re-review. The final
whole-branch review and the scoped event-wording re-review are approved, with
all findings addressed. Publication verifies the GitHub commit and tree against
the reviewed local files.
These tests validate orchestration with injected evidence; they do not establish
live specialist or provider acceptance.

Review regression tests cover unknown or substituted trace citations, appended
or replaced cached suites that relabel private cases, private finding targets,
stale coverage after adaptation, and truthful stage-entry events when an
operation fails. Public evidence is bound to canonical
policy provenance and the one frozen suite; later measured coverage supersedes
earlier provisional snapshots.

## Next integration steps

1. Task 20 adds the FastAPI routes, task runner, dependency container, lifespan
   cleanup, and safe status/error mapping around this coordinator. Cancel and
   drain asynchronous jobs on expiry/shutdown; direct store cleanup only
   invalidates outstanding writes.
2. Person 2 completes the asynchronous policy/revision wrappers. Interactive
   compilation must return three to five suggestions. The user confirms intent
   and severity; provisional model output cannot create that authority.
3. Person 3 supplies `ScenarioPlanner`. Its current sidecar client is a separate
   adapter and does not satisfy the frozen scenario-generation interface.
4. Person 4 supplies evaluation, finding analysis, deterministic metrics, patch
   application, and comparison through the frozen interfaces.
5. Task 21 records the real cached demonstration. Task 19 replay tests use
   explicitly synthetic injected records, not measured production evidence.

The revision planner is trusted Python code and receives canonical suite inputs
for hash validation. Person 2 must remove holdout cases and gold labels/answers
before calling the model. Workflow fake tests do not prove that adapter boundary.
Live provider acceptance, the full application demo, benchmark human review,
Gate B, and final recording remain pending.

## Historical Task 4 record

Task 4 shared interfaces and adapter infrastructure were completed and frozen as
version `1.0`; see `contracts/freeze-v1.json` and the integration reference.

## Task 4 interfaces

The normative integration reference is `contracts/task4-integration.md`. It lists
all eight stage protocols, exact provider-neutral fields, retry/repair rules,
configuration and Person 2's remaining wrapper work. Public imports are
`app.domain.models` and `app.domain.protocols`.

- Added `LLMRequest`, `LLMResponse`, `LLMOperation`, `LLMError`, `LLMErrorCode` and
  safe infrastructure exceptions/public projections.
- Added `InvariantSuggestion` / `InvariantSuggestions`: unconfirmed model intent,
  no severity or oracle fields, three-to-five validation and duplicate detection.
- Added `ScenarioBatch`, document-only `CompilePolicyRequest`, and additive
  `PolicyCompilation.invariant_drafts`. Deterministic compilation still requires
  a supplied extraction; its existing feature helper is unchanged.
- Added `Settings`, `ScriptedLLMClient`, `RetryingLLMClient` and `OpenAILLMClient`.
  Cached settings need no credentials. Every provider call uses the supplied
  original schema with `strict=False`; Pydantic feature validation is mandatory.
- Automatic transport retries are limited to two for timeout/rate-limit errors.
  SDK retries are disabled; one feature-level repair remains Person 2's work.

## Scope and verification

Task 4 changes shared domain/core code, its tests, generated schemas, the safe
root environment template and Person 1 contract documentation. Person 2 feature
code and Person 5 UI/submission artifacts are preserved. Existing HTTP OpenAPI
and the canonical completed `RunView` fixture remain byte-identical.

- Baseline before Task 4: 424 backend tests passed.
- Shared-model/protocol focused suite: 31 passed.
- Domain plus Person 2 compatibility suite: 386 passed.
- Individual JSON-schema registry: 111 models; exact generation checks pass.
- Adapter/protocol focused suite: 59 passed.
- Full backend regression suite: 511 passed.
- All 17 changed Python files pass their owned Ruff and formatting checks.
- Schema/OpenAPI export, canonical fixture and frontend generated-type checks pass.
- Shared-model independent review: spec PASS and quality APPROVED.
- Adapter and final integration review records are retained with the local task
  evidence; publication occurs only after required fixes are resolved.

No live provider was called, credentials were not created or changed, and no
private benchmark content was inspected. Fake tests establish mapping, validation
and budgets; they do not establish live model/schema compatibility.

## Person 2 handoff and downstream work

Read `contracts/task4-integration.md` and use the frozen types instead of adding
feature-local transport/protocol contracts. Implement the remaining
`complete_typed`, `extract_policy`, `LLMPolicyCompiler`, invariant generation and
`LLMRevisionPlanner` wrappers. Preserve deterministic validation after every model
response and populate extraction before calling the deterministic compiler.

The audit also identified two Person 2 trust-boundary follow-ups: reject or
normalize model-authored unsupported-clause confirmation, and sanitize parser
error chains/repair paths. These are feature work, not changes to the shared
protocol. Session confirmation and reviewer-owned severity stay in Person 1's
coordinator/API flow described above.

Person 3 can implement the typed scenario planner; Person 4 retains deterministic
evaluation/report/patch/comparison authority. Person 1 Task 20 wires the
public API and production container after the workflow is verified. Final live acceptance,
benchmark human review, Gate B and submission recording remain pending.

## Historical Task 3 record

Task 3 historical checkpoint. Its subsequent Gate A2 technical prerequisite was completed and published by Person 5; see the current Task 4 status above.

## Interfaces

Public models remain available through `app.domain.models`. Task 3 exports 105 concrete model schemas, the seven-operation OpenAPI registry, and one synthetic completed `RunView` fixture. Contract freeze still follows Task 4.

- `app.core.hashing.canonical_sha256(value)` is the sole canonical JSON hash helper. NFC normalization, sorted keys/sets, strict integer values, typed models, UUIDs and aware UTC timestamps are covered.
- `app.core.artifacts` provides complete/semantic projections, `make_artifact_envelope` and `validate_artifact_envelope`. Payload digests omit explicit self-digests; source/input/reference hashes remain significant. Semantic projections additionally omit named display/time/event fields. Parent contents require separate validation.
- `PublicComparisonMetrics` now carries all five aggregate assertion-transition buckets and a seven-check acceptance report. Duplicate acceptance/count fields must agree. Private assertion rows and gold labels remain outside `RunView`.
- Public benchmark wrappers are `BenchmarkSourceLabel`, `BenchmarkSourceLabels`, `BenchmarkExpectedRule`, and `BenchmarkCorrectedSemantics`. Corrected benchmark semantics carry expected rule content without fabricated citations or session approval.
- `scripts/validate_and_seal_blind_contracts.py` validates the exact seven-file archive format, schemas, source/quote hashes, counts, cross-references, suite and trace self-digests, and unchanged Gate A1 source/defect commitments. It writes only a public hash/count ledger, refuses overwrite, and reports fixed safe errors.

Complete commands, formats, HTTP mappings and hash preimages are documented in `contracts/README.md`.

## Files

- `backend/app/core/{hashing,artifacts}.py`
- `backend/app/domain/{export_schemas,contract_fixtures}.py`
- `backend/app/domain/models/{__init__,benchmark,evaluation,run}.py`
- `backend/tests/core/{test_hashing,test_artifacts}.py`
- `backend/tests/domain/{test_export_schemas,test_contract_fixtures,test_blind_schema_seal,test_run_models}.py`
- `scripts/validate_and_seal_blind_contracts.py`
- `contracts/{README.md,openapi.json,jsonschema/*.schema.json,fixtures/run-view.completed.json}`
- This handoff. No feature internals, frontend files, dependencies or private benchmark contents changed.

## Commands

Fresh final verification after review corrections, from `backend` unless stated:

- `.venv/bin/python -m pytest -q` — **369 passed, 1 existing Person 2 adapter test skipped**.
- `.venv/bin/python -m app.domain.export_schemas --check ../contracts/jsonschema --openapi ../contracts/openapi.json` — **exit 0**.
- `.venv/bin/python -m app.domain.contract_fixtures --check ../contracts/fixtures/run-view.completed.json` — **exit 0**.
- Ruff check and format check on all **15 changed Python files** — **passed**.
- Repository-wide Ruff — **11 existing findings in unchanged specialist files/tests**, identical to the Task 2 baseline. The full repository lint gate is not clean.

Implementation evidence:

- Hash/artifact unit tests: **48 passed**; initial missing-module RED and semantic/tamper regression coverage recorded.
- Schema/fixture/public-comparison tests: **66 passed**, including cross-process determinism, all seven HTTP operations, local refs, missing/changed/extra-file drift and check nonmutation.
- Final synthetic archive tests: **93 passed**. Review regressions first reproduced **three failures**, then passed: in-repository public seal layout, tampered trace self-hash, and changed trace content with a stale hash.
- No model/provider calls or actual evaluator execution were used. No real blind archive was read or resealed.

## Review and commits

- Previous Task 2 publication: `f220cc350fd07d8784e4178d043dd6e50242ce3e`.
- Local Task 3 commits: `56f764a` hashing/artifacts; `c5532e5` exports/fixture; `8aa93c2` schema-bound validator; `65ed3ff` public wrapper exports; `c7259bb` integration corrections.
- Independent hashing review passed. Whole Task 3 review approved schemas, fixture, privacy and hashing, and found two validator integration issues. Both are fixed and independently re-reviewed as addressed, with no new fix-related breakage.
- GitHub publication uses a separate integration commit preserving the existing remote history and verified file contents. No force push or unrelated teammate replacement is allowed.

## Submission evidence

Generated fixture data are conspicuously synthetic, in cached display mode, with all six effect states, five transition buckets and seven patch checks. A protected regression correctly makes the illustrated patch fail acceptance. Input hashes identify fixed labeled illustrative anchors; this is not an actual engine run, benchmark result or the later recorded cached-run deliverable.

Public Gate A1 metadata at `304145f2e35071135e7f43a7db1ba0383b858a4a` was rechecked using only its permitted timestamps, count and hashes. Its separate-agent authorship, late seal and pending human scoring approval remain disclosed. Task 3 does not repair historical blind-test timing or approve gold answers.

## Limitations and next work

1. Person 5 completes the separate Gate A2 custody action using the documented validator and unchanged private source/labels. Person 1 checks only the committed public metadata before Task 4; do not open private materials.
2. Task 4 provides protocols/configuration/provider adapters and the version 1.0 freeze. Regenerate schemas/fixture if its model changes require it.
3. Task 20 must implement the declared HTTP surface and safe error wrapper. The current OpenAPI is a contract registry, not running endpoints.
4. Person 2's existing adapter integration skip and the 11 pre-existing lint findings remain. Frontend code was not changed or re-tested in Task 3.
5. Runtime policy execution, interpretation quality, oracle correctness, parent lookup, actual run projection/sanitization and performance evaluation remain later work. Schema/custody validation does not establish these properties.

No real Gate A2 ledger, private corpus reveal, live-provider run, deployment or submission package was produced by Task 3.
