Status: In progress — contract-independent ingestion foundation complete

## Interfaces

- `prepare_policy_text(text, *, max_characters=50_000) -> PreparedPolicyText`
- `prepare_policy_pages(pages, *, max_characters=50_000, max_pages=20) -> PreparedPolicyText`
- `load_bundled_policy_text(path) -> PreparedPolicyText`
- `PreparedPolicyText` and `PreparedPolicyPage` are feature-local preparation
  types, not replacements for Person 1's shared `PolicyDocument` contract.

## Files

- `backend/app/features/policy/ingest.py`
- `backend/tests/features/policy/__init__.py`
- `backend/tests/features/policy/test_ingest.py`
- `team/person-2-policy/HANDOFF.md`

## Commands

- RED: `python -m pytest tests/features/policy/test_ingest.py -q`
  - Expected result: collection failed because `app.features.policy.ingest`
    did not exist.
- GREEN: `PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider tests/features/policy/test_ingest.py -q`
  - Result: 12 passed.
- FULL: `PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider -q`
  - Result: 27 passed.
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

## Limitations

- Person 1's shared domain contracts, canonical hashing helper, and public
  protocols are not yet present on `main`. This foundation intentionally does
  not create competing contracts or compute the final document hash.
- `prepare_policy_pages` accepts page text already extracted by a PDF parser.
  Selecting and adding a PDF dependency belongs to the shared dependency owner.
- The public `ingest_policy_text(...) -> PolicyDocument` adapter from Task 12
  remains pending until the frozen shared contracts are available.
