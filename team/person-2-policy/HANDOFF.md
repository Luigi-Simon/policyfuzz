# Person 2 — Policy Intelligence handoff

## Citation boundary correction — 2026-09-06

Branch: `p2/fix-citation-metadata`. Changes are ready for Person 1's integration
commit; Person 2 made no commit or live provider call.

The recorded development diagnostic had 11 exact source quotes but incorrect
model-authored hashes/offsets. The provider now selects Python-issued citation
handles. Public `SourceSpan`, extraction/compiler APIs, exact validators, and
deterministic fixture behavior remain unchanged.

- `build_citation_catalog(document)` returns an immutable `CitationCatalog` with
  ordered `(citation_handle, span)` entries and exact-membership `resolve(handle)`.
  Handles bind the document content/layout and exact source location using
  canonical SHA-256. Quotes/hashes/global offsets are derived by Python from
  normalized bounded source; identical text at different locations stays distinct.
- Private `ModelRuleDraft` carries semantic fields, required `rule_handle`, and
  `citation_handle`; `ModelUnsupportedClause` carries its existing scope/reason
  fields plus `citation_handle`. Neither exposes a public span/provenance alternative.
  Python resolves handles, revalidates frozen public models, and checks the override
  graph. Unknown/foreign citations and non-rule override aliases fail closed.
- The prompt sends source quotes once in a catalog with page/global offsets.
  Up to 512 nonempty lines stay separate; larger inputs group adjacent lines
  without crossing pages or discarding tail content, yielding at most 532 entries
  for a 50,000-character/20-page document. This is structural segmentation, not
  clause interpretation. Long/grouped citations can cover multiple clauses.
- One schema repair remains the maximum. Invalid citation handles, semantic
  constraints, and invalid normalized graphs are terminal sanitized errors;
  Python does not guess replacement citations or repair model semantics.

Changed implementation: `citations.py`, `model_io.py`, `prompts.py`, and
`extraction.py` under `backend/app/features/policy/`. Tests: new
`test_citation_catalog.py`, updated `test_compiler.py`,
`test_extraction_validation.py`, and `test_prompts.py` under the matching test
directory. Documentation: this handoff and `prompt-requirements.md`.

New provider fixture: `team/person-2-policy/fixtures/development-provider-extraction.json`.
Person 1 should point `scripts/demo_support.py` at it. The existing
`development-extraction.json` remains unchanged for deterministic APIs. Independent
fixture review confirmed 10 rules, one unsupported clause, unchanged compiled rule
IDs and unsupported content. Provider-derived citation IDs change complete artifact
hashes, so Person 1 owns cache/evidence regeneration and integration checks.

Verification (run from `backend`, using `.venv/bin/python`):

- TDD: initial 16 catalog/wire regressions failed before implementation; further
  failing regressions caught trusted long-source expansion and two override
  normalization errors. The final catalog test file contains 20 cases.
- `-m pytest tests/features/policy -q --tb=short`: **151 passed**.
- `-m ruff check app/features/policy tests/features/policy`: **passed**.
- `-m ruff format --check app/features/policy tests/features/policy`:
  **26 files already formatted**.
- The recorded diagnostic's original semantic fields hydrate into 10 rules and
  one unsupported clause with all 11 exact citations in one fake provider response.

Remaining limits: a valid citation handle proves source provenance, not semantic
extraction quality or coverage. No policy wording, benchmark labels, blind data,
scoring, confirmation, shared contracts, or provider integration was changed by
Person 2. Person 1 owns full-backend verification and supervised live evidence.

Status: Complete for Tasks 12–15 and Person 2's Task 21 ownership

Current branch: `p2/refactor-complete-policy-intelligence`

## Executive summary

Person 2 provides safe text ingestion, exact citation validation, typed extraction,
deterministic rule and policy identities, provisional invariant suggestions, and
minimal revision proposals through the frozen provider-neutral protocols. Schema
validation permits one sanitized repair request. Python recomputes semantic IDs,
forces model-authored unsupported clauses to provisional status, and restricts
revision prompts to accepted visible evidence without scenario assertions or
holdout cases. Person 4 continues to own revision application and evaluation.

The development and corrected-control policy artifacts now implement the Task 21
synthetic benchmark contract. Reproducible extraction, invariant-suggestion, and
three-operation revision-proposal responses are stored under
`team/person-2-policy/fixtures/` for offline replay.

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
- `compile_baseline_policy(request) -> PolicyCompilation` deterministically
  assembles a provisional `PolicyIR`, preserves unsupported clauses, and reports
  exclusions without invoking a model.
- `build_invariant_suggestion_prompt(policy) -> InvariantSuggestionPrompt`
  prepares three-to-five unverified suggestions without defining a competing
  shared output contract.
- `validate_revision_proposal(request, proposal) -> ValidatedRevisionProposal`
  validates evidence eligibility, visible-only witnesses, artifact anchors,
  rule targets and revisions, recomputes proposal/add-rule IDs, and labels draft
  wording AI-generated and unverified.
- `build_revision_prompt(request) -> RevisionPrompt` projects only accepted,
  non-candidate findings and visible scenarios for the future model boundary.

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
- `backend/app/features/policy/compiler.py`
- `backend/app/features/policy/revision.py`
- `backend/tests/features/policy/test_compiler.py`
- `backend/tests/features/policy/test_revision.py`
- `backend/tests/features/policy/test_pipeline.py`
- `backend/tests/features/policy/test_prepared_fixtures.py`
- `team/person-2-policy/fake-llm-responses.json`
- `team/person-2-policy/invariant-suggestion-fixtures.json`
- `team/person-2-policy/revision-proposal-fixtures.json`
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
- Revision inputs reject stale request/proposal anchors, candidate findings,
  rejected decisions, holdout witnesses, unknown rules, stale revisions, and
  invalid override dimensions. Proposal application remains outside Person 2.
- Cross-process tests verify stable document, rule, and policy identities.
- Development fixture metadata now records its exact source SHA-256 and remains
  explicitly provisional and unverified.

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
- Deterministic compiler/revision/pipeline RED: collection failed for the missing
  compiler, invariant prompt, and revision modules.
- Deterministic compiler/revision/pipeline GREEN: complete Person 2 suite
  **109 passed**.
- Current full backend: **421 passed, 3 failed**. The same Person 1-owned
  enum/schema/warning failures remain under the active Pydantic environment.
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
- Person 1's present `InvariantDraft` requires session-confirmed assertions, so
  invariant model-output validation intentionally remains fixtures and prompt
  preparation until a provisional shared output shape is frozen.
- Person 4 owns deterministic proposal application; Person 2 only validates and
  prepares unverified proposals.
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

## Final Task 4 and Task 21 completion update

This section supersedes the historical integration limitations and request above.
The frozen Task 4 interfaces are now integrated:

- `complete_typed(...)` validates either object or text output, performs at most
  one repair, sends only bounded schema paths/codes, and raises a terminal safe
  error with `repair_attempted=True`.
- `extract_policy(...)` builds a separated-trust `LLMRequest`, validates exact
  citations, and returns the bounded typed extraction.
- `LLMPolicyCompiler(llm).compile(...)` implements `PolicyCompiler`, performs
  extraction when needed, validates three to five suggestions, and replaces
  model-supplied suggestion and assertion IDs with canonical semantic IDs.
- `LLMRevisionPlanner(llm).propose(...)` implements `RevisionPlanner`, accepts the
  canonical full request, sends the model only accepted visible findings and
  visible scenario facts, and returns a deterministically validated proposal.

Final synthetic artifact anchors:

- Development document SHA-256:
  `4c194c07ac6de7044f0548771ea257cccd1e8d4d0a5b4d1a602e428ee3a66734`
- Development complete policy SHA-256:
  `0dce41090a250a7e82f93a292d3aaf84093d0a6adc42f20a3c582ed0ebbfa7c8`
- Corrected-control document SHA-256:
  `1b5a96f1b897fe1f78f46a6e8d956f4470b8f2c321021e8dc96d5ad3b7ef566c`
- Corrected-control complete policy SHA-256:
  `81e870cc9734a2e2acb875dc7808ed4e9ca69ca77c2e32930c9444aa2c19b728`
- Confirmed contract complete SHA-256:
  `d182dc79ab8133b25876e7adc0047f590b72d2642e6f46ac46987972df00ce3a`

No live provider was called. Revision application, deterministic evaluation,
workflow/API wiring, recorded cached-run assembly, and benchmark execution labels
remain with their assigned owners.

## Final policy-stage hardening update

Person 2's standalone stage now rejects invalid proposals before they reach the
workflow or Person 4. Every accepted finding must be targeted by at least one
operation, an operation may reference only eligible findings without duplicates,
one rule may be changed at most once per proposal, and deterministic IDs for
added rules cannot collide with baseline or earlier added rules.

Extraction now closes the executable override graph after citation validation
and the 12-rule cap. If an override target is removed, every dependent rule is
removed transitively and preserved with its verified citation as an
`unsupported_logic` clause. This prevents a validated extraction from failing
later because it contains a dangling override reference.

This update does not apply revisions or assign confirmation. Person 2 returns a
validated, AI-generated and unverified proposal. Person 4 remains responsible
for deterministic atomic application, revision increments, session provenance,
re-evaluation, and comparison; Person 1 owns workflow/API orchestration.

Hardening files:

- `backend/app/features/policy/extraction.py`
- `backend/app/features/policy/revision.py`
- `backend/tests/features/policy/test_extraction_validation.py`
- `backend/tests/features/policy/test_revision.py`
- `team/person-2-policy/HANDOFF.md`

Hardening verification:

- RED revision suite: **3 failed, 13 passed**, proving missing coverage for
  untargeted accepted findings, repeated source-rule changes, and colliding
  deterministic add-rule IDs.
- GREEN focused extraction/compiler/rule-ID suite: **28 passed**.
- Complete Person 2 suite: `uv run --frozen --extra dev python -m pytest -p
  no:cacheprovider tests/features/policy -q` — **131 passed**.
- Full backend regression: `uv run --frozen --extra dev python -m pytest -p
  no:cacheprovider -q` — **1,442 passed**.
- Person 2 Ruff check: **passed**; Ruff format check: **25 files already
  formatted**.
