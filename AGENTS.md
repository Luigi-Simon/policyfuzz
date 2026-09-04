# PolicyFuzz repository rules

These rules apply to every path unless a more specific `AGENTS.md` narrows them.

## Engineering discipline

- Use test-driven development: write a focused failing test, verify the expected failure, implement the minimum change, and rerun the relevant suite.
- Import public domain models only from `app.domain.models`, stage protocols only from `app.domain.protocols`, and canonical hashing only from `app.core.hashing.canonical_sha256`.
- Unit and integration tests must use fakes and must never call a live model provider.
- The evaluation feature is deterministic Python and must never import, configure, or call an LLM.
- Use only synthetic or explicitly non-confidential T&E data. Never commit real policies, pasted uploads, private blind materials before reveal, secrets, `.env`, caches, virtual environments, or build output.

## Collaboration and Git

- Single-writer ownership is mandatory. Edit only paths owned by your work packet; coordinate shared files through Person 1.
- Use short-lived branches named `pN/type-description`, where `N` is the person number.
- Use conventional commit prefixes such as `feat:`, `fix:`, `test:`, `docs:`, `chore:`, and scoped variants.
- Person 1 owns shared contracts, integration surfaces, root configuration, and the merge queue.
- Person 1 owns shared `scripts/**` except `scripts/verify_submission.py`; Person 5 is the sole writer of that Task 24 verifier, which Person 1 only consumes during Task 25.
- Every handoff records public interfaces, changed files, commands and results, submission evidence, and limitations.

## Product trust boundaries

- LLM-backed policy and fuzzing stages may interpret or generate, but cannot assign authoritative verdicts, severity, metrics, or scored answers.
- Evaluation, artifact validation, hashing, suite freezing, metrics, and patch acceptance remain deterministic.
- Do not expose prompts, chain-of-thought, credentials, full pasted documents, or blind labels through public artifacts.
