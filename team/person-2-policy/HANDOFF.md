Status: In progress — ingestion foundation and compiler preparation complete

## Interfaces

- `prepare_policy_text(text, *, max_characters=50_000) -> PreparedPolicyText`
- `prepare_policy_pages(pages, *, max_characters=50_000, max_pages=20) -> PreparedPolicyText`
- `load_bundled_policy_text(path) -> PreparedPolicyText`
- `validate_citation(*, pages, page_number, start_offset, end_offset, quote, quote_sha256) -> ValidatedCitation`
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
  - Result after primitive citation validation: 41 passed, 1 skipped
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
- Every rule and unsupported clause in the development fixture now has an exact
  source offset and independently verified quote hash.

## Limitations

- Person 1's shared domain contracts, canonical hashing helper, and public
  protocols are not yet present on `main`. This foundation intentionally does
  not create competing contracts or compute the final document hash.
- `prepare_policy_pages` accepts page text already extracted by a PDF parser.
  Selecting and adding a PDF dependency belongs to the shared dependency owner.
- The public `ingest_policy_text(...) -> PolicyDocument` adapter from Task 12
  remains pending until the frozen shared contracts are available.
- Citation tests are contract-first and use `pytest.importorskip`; they will
  become executable when Person 1's `SourceSpan` and the policy citation module
  are available.
