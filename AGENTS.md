# PolicyFuzz repository rules

## V2 collaboration scope — current branch

The user-approved v2 work is split between Simon and the Sandbox contributor.
Read docs/v2/README.md and the applicable team/v2-core or team/v2-sandbox handoff.

- V2 has exactly four product agent roles: **Orchestrator Agent**, **Metric Agent**, **Sandbox Agent**, **Judge Agent**. The old Fuzz Agent role is named Metric Agent in v2. PolicyFuzz remains the project name.
- Parsing, translation, deterministic execution and storage are tools, not extra agent roles. Stakeholders are participants inside the Sandbox Agent.
- Simon owns shared schemas, configuration and integration, plus all v2 paths except the friend's Sandbox and Judge implementation/test paths.
- The friend owns backend/app/v2/sandbox/**, backend/tests/v2/sandbox/**, backend/app/v2/judge/** and backend/tests/v2/judge/**. Use separate Sandbox and Judge feature branches. Shared schema or dependency changes go through Simon.
- Canonical v2 models come from app.v2.contracts (Sandbox), app.v2.metric_contracts (Metric) and app.v2.judge_contracts (Judge); protocols come from app.v2.protocols and app.v2.judge_protocols. This is an explicit versioned exception to the v1 import rule below.
- V2 work uses synthetic or explicitly non-confidential policy text. The executable domain is limited to what the runner actually supports; no general-policy correctness claim.
- Preserve v1 schemas, recorded artifacts and historical hashes. Legacy v1 modules retain their names until a separately tested migration is integrated.
- Do not send expected verdicts or historical outcomes into stakeholder seed material.
- Keep main unchanged during v2 foundation work. Core and Sandbox PRs target p1/feat-policyfuzz-v2.
- Unit tests and fixtures must make no live provider calls. Fixture results must always identify themselves as fixture.
- Public Sandbox output contains English display text; original records remain backend-only. Translation cannot assign policy verdicts or alter IDs, counts, amounts or source relationships.
- This scope supersedes the older five-person ownership allocation only for the new v2 work. The v1 rules below continue to apply to the preserved v1 application.

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
