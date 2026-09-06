# Person 2 — Policy Intelligence handoff

Status: Deterministic Stage 1–2 foundation and extraction fixture suite complete

Current branch: `p2/test-extraction-fixtures`

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
- `to_policy_pages(prepared) -> tuple[PolicyPage, ...]` maps normalized prepared
  pages into Person 1's immutable contract without constructing or hashing a
  `PolicyDocument`.
- `ingest_policy_text(title, text, source_type) -> PolicyDocument` constructs a
  normalized, bounded document with a content-derived ID and the raw UTF-8
  source hash required by Person 1's contract.
- `load_bundled_policy(path) -> PolicyDocument` provides the same contract for
  checked-in synthetic policy samples.
- `assign_baseline_rule_ids(document, drafts) -> tuple[Rule, ...]` validates
  citations and assigns full canonical hashes over rule semantics plus the
  canonical source-span hash. Display wording, confidence, and model-supplied
  citation IDs do not influence semantic identity.

Existing foundation remains available for normalized bounded ingestion, strict
typed JSON parsing, primitive citation validation, and bounded policy retrieval.

## Changed files

- `backend/app/features/policy/citations.py`
- `backend/app/features/policy/extraction.py`
- `backend/app/features/policy/prompts.py`
- `backend/tests/features/policy/test_citations_contract_draft.py`
- `backend/tests/features/policy/test_extraction_validation.py`
- `backend/tests/features/policy/test_prompts.py`
- `backend/app/features/policy/ingest.py`
- `backend/tests/features/policy/test_ingest.py`
- `backend/tests/features/policy/test_extraction_fixtures.py`
- `backend/tests/features/policy/test_rule_ids.py`
- `team/person-2-policy/fake-llm-responses.json`
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
- Synthetic fake outputs cover exact citations, invalid hashes and offsets,
  unsupported clauses, invalid predicates and effects, prompt injection,
  13-rule overflow, and OR expansion into two distinct AND-only rules.
- Prepared page text and global offsets transfer directly into `PolicyPage`;
  this adapter does not calculate or accept a document hash.
- Contract document identity is calculated from normalized source text using
  ordinary raw UTF-8 SHA-256, as required by `contracts/README.md`; structured
  rule signatures use `app.core.hashing.canonical_sha256` exclusively.
- Baseline rule IDs exclude model-authored display metadata, use revision zero,
  reject invalid citations, and reject duplicate semantic/span identities.

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
- Fixture/mapping RED: collection failed because `to_policy_pages` did not exist.
- Fixture/mapping GREEN: `PYTHONDONTWRITEBYTECODE=1 python -m pytest -p
  no:cacheprovider tests/features/policy/test_ingest.py
  tests/features/policy/test_extraction_fixtures.py -q` — **22 passed**.
- Current Person 2 suite with fixtures: **80 passed**.
- Document/rule-ID RED: focused collection failed for missing
  `ingest_policy_text` and `assign_baseline_rule_ids`.
- Document/rule-ID GREEN: focused suite **22 passed**; current complete Person 2
  suite **89 passed**.
- Current full backend: **401 passed, the same 3 Person 1-owned failures**
  described above.
- Full backend after that rebase: **382 passed, 3 failed**. The failures are in
  Person 1-owned Task 2/3 checks: enum construction, committed schema drift,
  and warning-free blind-validation stderr. The active environment emits a
  Pydantic protected-namespace warning and does not match Person 1's schema
  generation environment; Person 2 did not change shared models or schemas.
- Ruff could not run because the active Python environment has no `ruff` module.

## Remaining integration limitations

- Person 1's canonical hashing helper is integrated for stable baseline rule
  identity, and contract-backed `PolicyDocument` construction is complete.
- The one-repair model workflow and end-to-end `extract_policy(...)` still
  require Person 1's public LLM request/response/operation types and
  `app.domain.protocols.LLMClient` from Task 4.
- No live model was called. No shared contracts, dependencies, API, workflow,
  fuzzing, evaluation, frontend, blind data, or submission files were changed.

## Request to Person 1

Please complete Task 4 and freeze the shared integration interfaces:

1. Publish `app.domain.protocols.LLMClient` and `PolicyCompiler`.
2. Publish the typed LLM request, response, operation, and error contracts.
3. Publish the scripted/fake client and retry behavior for feature tests.
4. Confirm the provider-neutral request shape that carries our separated system
   prompt, policy payload, and response schema.

This is Person 1's responsibility because these modules are shared integration
surfaces and root configuration. Person 2 must not create competing protocols,
provider adapters, dependency changes, or workflow contracts. Once frozen,
Person 2 can connect the completed deterministic ingestion, citation checks,
prompt builder, and rule-ID assignment to the one-repair extraction workflow;
Person 3 can then consume the validated extraction output.
