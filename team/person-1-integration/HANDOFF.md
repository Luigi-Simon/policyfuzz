Status: Task 2 complete; independently reviewed and verified. Task 3 is next.

## Interfaces

Public import boundary: `app.domain.models`. Local implementation commit: `4dc41ee` (`feat: define PolicyFuzz domain contracts`); reviewed fixes: `bfc3dd8` (`fix: align bounded contracts and public review evidence`). Exports include all 21 frozen request/report names from Task 2, 102 concrete model classes (147 total exports), finite field/effect/status types, immutable nested contracts, typed artifact payloads, and dedicated public `RunView` summaries. The GitHub integration publishes the verified final file contents in its own commit.

`SourceSpan` constructor: `page`, `start`, `end`, `quote`, `quote_sha256`, optional `section`. Baseline rule provenance is text-cited. Proposed changes use `RevisionRuleDraft`; session provenance is created only after confirmation. Comparison/acceptance reports require both baseline and revised `InputHashes`.

## Files

- `backend/app/domain/models/{__init__,common,llm,policy,scenario,evaluation,revision,run}.py`
- `backend/tests/domain/{factories,test_policy_models,test_scenario_models,test_evaluation_models,test_revision_models,test_run_models}.py`
- This handoff.

## Review corrections

- Enforced the approved 50,000 pasted-character limit and global 12-rule `PolicyIR` limit for both baseline and revision. The earlier 100,000-character choice was incorrect and is superseded. Existing limits remain 15 scenarios and 1–3 operations.
- `ContractConfirmation` exposes typed baseline rule/invariant reviews, required dimensions, baseline ID/artifact hash, and document hash. `ConfirmContractRequest` confirms the server-held baseline by ID/artifact hash and submits typed reviewed intent; it no longer accepts full `PolicyIR`. Invariant `AssertionContent` contains no private oracle origin/label references.
- `RevisionOperationSummary` contains the authoritative typed operation and matching before-rule for replacements/overrides. `RunView` now represents visible unsupported-clause/rejection source spans, finite reasons and dispositions, plus per-scenario/per-dimension execution traces. `HoldoutEvidenceSummary` allows only aggregate counts/effect states; detailed evidence rejects holdout rows.
- Corrected the frozen export count to 21. The existing local Task 2 report was removed from the Git index while retained locally; it is not a changed Git artifact.

## Commands

Fix-round evidence:

- `backend/.venv/bin/python -m pytest backend/tests/domain/test_policy_models.py backend/tests/domain/test_run_models.py -q`: **RED 10 failed, 70 passed** → **GREEN 80 passed**.
- `backend/.venv/bin/python -m pytest backend/tests/domain -q`: final **133 passed in 0.69s**.
- From `backend`, `.venv/bin/ruff check app/domain/models tests/domain --output-format concise`: **all checks passed**.
- From `backend`, `.venv/bin/ruff format --check app/domain/models tests/domain`: **15 files already formatted**.
- All **102** concrete exported model schemas generate in memory; no exporter or schema files added. `git diff --check`: clean.
- Root's fresh final whole-backend verification, from `backend`: `.venv/bin/python -m pytest -q` — **208 passed, 1 existing adapter test skipped**. Owned Ruff/format checks passed again. No provider calls.
- Independent review found four Important contract issues; all four were fixed and independently re-reviewed as addressed, with no new Important findings. A focused privacy probe additionally confirmed that raw private assertion instances cannot enter the public invariant model.

Original delivery evidence (before this fix):

- `backend/.venv/bin/python -m pytest backend/tests/domain -q`: initial RED had 4 missing-export collection errors; final focused run **118 passed**.
- From `backend`, `.venv/bin/python -m pytest -q`: **193 passed, 1 skipped**.
- From `backend`, `.venv/bin/ruff check app/domain/models tests/domain --output-format concise`: **all checks passed**.
- From `backend`, `.venv/bin/ruff format --check app/domain/models tests/domain`: **15 files already formatted**.
- From `backend`, `.venv/bin/ruff check app tests --output-format concise`: **11 pre-existing findings in untouched specialist files/tests**. No specialist files were modified.
- `git diff --check`: clean. All 97 concrete exported model schemas generate in memory. JSON round trips and nested immutability pass.

Exact RED/GREEN iterations, interface decisions, and original lint paths are recorded in the existing local Task 2 report.

## Submission evidence

Task 2 used synthetic fixtures only and made no live provider calls. Implementers and reviewers did not read actual blind benchmark/archive/labels, engine sidecar contracts, or the full implementation plan. Root verified public Gate A1 metadata at local base `8ff4528b4bfac026c0fa3db01e32c408600c4e7e`, tree-identical to published `304145f2e35071135e7f43a7db1ba0383b858a4a`; this remains a disclosed late, agent-authored seal with human scoring approval pending. Root integrates the reviewed contents without force-pushing or replacing unrelated teammate changes.

## Limitations and merge order

1. Task 2 review and verification are complete; the public contract freeze still waits for Tasks 3–4.
2. Task 3 implements canonical hashing/artifact validation/schema export and drift gates.
3. Verify separate Gate A2 before Task 4 protocol/provider work.
4. Integrate Person 2 primitives through explicit adapters; the existing integration skip remains.
5. Specialists/coordinator later enforce runtime provenance, server-side decision/severity eligibility, coverage/count calculations, hash anchoring, revision application, safe projections, and private scoring. Confirmation must validate the exact server-held baseline ID/artifact hash; projectors must route private clauses, rejections and traces to aggregate holdout evidence and sanitize free text/source excerpts. Model shape alone cannot verify a truthful visible partition.

No hashing, schema files/exporter, protocols, provider integration, features, frontend, engine, coordinator, or submission packaging were added in this task.
