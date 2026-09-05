Status: Ready for review — contract-independent Policy Intelligence foundation complete

Branch: `p2/feat-policy-ingestion`

Commits after the ingestion commit already on `main`:

- `7b1bf3a` — compiler fixtures, vocabulary, sample policy, and prompt requirements
- `21c9ee1` — primitive exact-citation validation
- `d7e3580` — strict typed model-output validation
- `6cfaa8b` — bounded compiler retrieval tools

## Interfaces

- `prepare_policy_text(text, *, max_characters=50_000) -> PreparedPolicyText`
- `prepare_policy_pages(pages, *, max_characters=50_000, max_pages=20) -> PreparedPolicyText`
- `load_bundled_policy_text(path) -> PreparedPolicyText`
- `validate_citation(*, pages, page_number, start_offset, end_offset, quote, quote_sha256) -> ValidatedCitation`
- `parse_typed_output(raw_output, *, response_model, max_characters=100_000) -> BaseModel`
- `read_page(policy, *, page_number, max_characters=5_000) -> PageExcerpt`
- `search_policy(policy, query, *, max_results=5, context_characters=120) -> tuple[SearchHit, ...]`
- `find_section(policy, section_name, *, max_characters=3_000) -> SectionExcerpt`
- `get_clause_context(policy, *, page_number, start_offset, end_offset, context_characters=120) -> PageExcerpt`
- `PreparedPolicyText` and `PreparedPolicyPage` are feature-local preparation
  types, not replacements for Person 1's shared `PolicyDocument` contract.

## Files

- `backend/app/features/policy/ingest.py`
- `backend/tests/features/policy/__init__.py`
- `backend/tests/features/policy/test_ingest.py`
- `team/person-2-policy/HANDOFF.md`
- `backend/tests/features/policy/test_citations_contract_draft.py`
- `backend/app/features/policy/citations.py`
- `backend/tests/features/policy/test_citations.py`
- `backend/app/features/policy/model_output.py`
- `backend/tests/features/policy/test_model_output.py`
- `backend/app/features/policy/tools.py`
- `backend/tests/features/policy/test_tools.py`
- `samples/policies/development-policy.txt`
- `team/person-2-policy/expected-extracted-rules.json`
- `team/person-2-policy/supported-vocabulary.md`
- `team/person-2-policy/fake-llm-responses.json`
- `team/person-2-policy/prompt-requirements.md`

## Commands

- RED: `python -m pytest tests/features/policy/test_ingest.py -q`
  - Expected result: collection failed because `app.features.policy.ingest`
    did not exist.
- GREEN: `PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider tests/features/policy/test_ingest.py -q`
  - Result: 12 passed.
- FULL: `PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider -q`
  - Result after compiler retrieval tools: 69 passed, 1 skipped
    (only the future shared-contract adapter tests remain skipped).
- JSON validation: `python -m json.tool team/person-2-policy/expected-extracted-rules.json` and `python -m json.tool team/person-2-policy/fake-llm-responses.json`
  - Result: both valid.
- LINT: `python -m ruff check app/features/policy/ingest.py tests/features/policy/test_ingest.py`
  - Not run: `ruff` is declared as a development dependency but is not
    installed in the current environment.

## Submission evidence

- Unicode is normalized to NFC and CRLF/CR line endings become LF.
- Empty policies, blank extracted pages, more than 20 pages, invalid UTF-8,
  missing files, and policies over 50,000 normalized characters are rejected
  with sanitized stable error codes.
- Prepared pages retain deterministic one-based page numbers and global
  character offsets into the combined normalized text.
- Primitive citation validation rejects invalid pages, offsets, quote text, and
  SHA-256 values using sanitized error codes.
- Typed model-output parsing strictly validates JSON against a caller-supplied
  Pydantic model and exposes only deterministic field paths and error codes.
- Malformed, empty, oversized, schema-invalid, and coercion-dependent model
  output is rejected without echoing raw output or private values.
- Every rule and unsupported clause in the development fixture now has an exact
  source offset and independently verified quote hash.
- Prompt requirements record the broader large-population stakeholder audience
  while preserving the repository's current T&E MVP scope.
- Compiler retrieval tools provide bounded page reads, literal case-insensitive
  search, numbered-section lookup, and clause context with stable offsets.
- Retrieval failures use sanitized error codes and do not include policy text.

## Limitations

- Person 1's shared domain contracts, canonical hashing helper, and public
  protocols are not yet present on `main`. This foundation intentionally does
  not create competing contracts or compute the final document hash.
- `prepare_policy_pages` accepts page text already extracted by a PDF parser.
  Selecting and adding a PDF dependency belongs to the shared dependency owner.
- The public `ingest_policy_text(...) -> PolicyDocument` adapter from Task 12
  remains pending until the frozen shared contracts are available.
- Contract-adapter citation tests remain skipped until Person 1's `SourceSpan`
  model exists. Primitive citation tests are active and passing.

## Integration handoff

Person 1 needs to publish the documented shared `PolicyDocument`, `PolicyPage`,
`SourceSpan`, `RuleDraft`, `PolicyExtraction`, request/response models,
`canonical_sha256`, and public LLM protocol. Person 2 should then:

1. Adapt `PreparedPolicyText` to the official `PolicyDocument` and compute its
   canonical document hash.
2. Add `validate_source_span(document, span)` as a thin adapter over the tested
   primitive citation validator and enable the skipped tests.
3. Wrap `parse_typed_output` in the one-repair LLM workflow.
4. Use the bounded retrieval tools in the Policy Compiler Agent.

No file outside Person 2's owned paths is changed by this branch. The local
`person-2-policy-flow.svg` diagram is untracked and is not part of this handoff.
