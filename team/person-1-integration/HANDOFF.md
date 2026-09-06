# Person 1 integration handoff

Status: Task 4 shared interfaces and adapter infrastructure are complete and
frozen as version `1.0`; see `contracts/freeze-v1.json` and the integration reference.

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
future coordinator/API flow.

Person 3 can implement the typed scenario planner; Person 4 retains deterministic
evaluation/report/patch/comparison authority. Person 1 Tasks 19–20 still wire the
coordinator and public API after specialists integrate. Final live acceptance,
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
