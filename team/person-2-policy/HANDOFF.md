# Person 2 — Policy Intelligence handoff

Status: Deterministic Stage 1–2 foundation integrated with Person 1's Task 2 contracts

Branch: `p2/feat-policy-stages-1-2`

## Public inputs and outputs

- Consumes `PolicyDocument`, `SourceSpan`, `PolicyExtraction`, `RuleDraft`,
  `TextRuleProvenance`, and `UnsupportedClause` from `app.domain.models`.
- `validate_source_span(document, span) -> ValidatedCitation` checks an exact
  contract citation using document-global offsets and its declared page.
- `validate_policy_extraction(document, extraction, *, max_rules=12) ->
  ValidatedPolicyExtraction` preserves valid rules and unsupported clauses,
  excludes invalidly cited rules, and reports the deterministic exclusion count.
- `parse_and_validate_policy_extraction(document, raw_output)` strictly validates
  raw JSON against Person 1's predicate/effect contracts before provenance checks.
- `build_policy_extraction_prompt(document) -> PolicyExtractionPrompt` returns
  separated system instructions, untrusted policy JSON, and a JSON schema
  generated directly from Person 1's `PolicyExtraction` contract.

Existing foundation remains available for normalized bounded ingestion, strict
typed JSON parsing, primitive citation validation, and bounded policy retrieval.

## Changed files

- `backend/app/features/policy/citations.py`
- `backend/app/features/policy/extraction.py`
- `backend/app/features/policy/prompts.py`
- `backend/tests/features/policy/test_citations_contract_draft.py`
- `backend/tests/features/policy/test_extraction_validation.py`
- `backend/tests/features/policy/test_prompts.py`
- `team/person-2-policy/HANDOFF.md`

## Deterministic behavior and trust boundaries

- Source-span validation converts global offsets to page-local offsets only
  after confirming that the span lies wholly inside its declared page.
- Exact quote equality and SHA-256 are recomputed from source policy text.
- A bad executable-rule citation excludes only that rule. Python derives a
  verified line-level source span and preserves the candidate as an
  `invalid_citation` unsupported clause.
- Existing unsupported clauses are retained only when their citations validate.
- At most 12 valid rules pass this boundary; overflow is counted as excluded.
- Prompt instructions and policy content remain separate. Policy text is
  explicitly untrusted, JSON-only output is required, OR clauses must become
  separate AND-only rules, and unsupported language must not be guessed.
- The prompt cannot assign authoritative verdicts, severity, metrics,
  confirmation, approval, or legal conclusions.

## Commands and results

- RED: focused test collection failed for missing `validate_source_span`,
  `app.features.policy.extraction`, and `app.features.policy.prompts`.
- GREEN: `PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider
  tests/features/policy/test_citations.py
  tests/features/policy/test_citations_contract_draft.py
  tests/features/policy/test_extraction_validation.py
  tests/features/policy/test_prompts.py -q` — **27 passed**.
- Person 2 suite after rebasing onto Person 1's Task 3 commit:
  `PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider
  tests/features/policy -q` — **70 passed**.
- Full backend after that rebase: **382 passed, 3 failed**. The failures are in
  Person 1-owned Task 2/3 checks: enum construction, committed schema drift,
  and warning-free blind-validation stderr. The active environment emits a
  Pydantic protected-namespace warning and does not match Person 1's schema
  generation environment; Person 2 did not change shared models or schemas.
- Ruff could not run because the active Python environment has no `ruff` module.

## Remaining integration limitations

- Contract-backed `PolicyDocument` creation and stable rule IDs still require
  Person 1's `app.core.hashing.canonical_sha256` from Task 3.
- The one-repair model workflow and end-to-end `extract_policy(...)` still
  require Person 1's public LLM request/response/operation types and
  `app.domain.protocols.LLMClient` from Task 4.
- No live model was called. No shared contracts, dependencies, API, workflow,
  fuzzing, evaluation, frontend, blind data, or submission files were changed.
