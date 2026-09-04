# Person 1 — Integration lead
## Mission

Own shared contracts and infrastructure, wire the modular monolith through public interfaces, and keep the merge queue reproducible.

## Paths owned

- Root files and CI; `contracts/**`; `backend/pyproject.toml`; `backend/app/{main.py,container.py,api/**,core/**,domain/**,workflow/**}`; corresponding Person 1 tests; `samples/cached-demo/**`; all shared `scripts/**` except `scripts/verify_submission.py`; and `team/person-1-integration/**`.
- Shared integration tests and generated public contract fixtures.

## Paths prohibited

- Do not implement specialist internals in `backend/app/features/{policy,fuzzing,evaluation}` or their unit tests.
- Do not edit frontend dependencies/UI or final submission source; read other persons' handoffs only unless a planned shared step says otherwise.
- Do not edit `scripts/verify_submission.py`; Person 5 is its narrow exclusive owner for Task 24, and Person 1 only consumes the verifier and its output during Task 25.
- Do not create, inspect, reveal, or commit private blind policy/labels.

## Public inputs and outputs

- Consume only specialist stage protocols and public domain models.
- Produce `app.domain.models`, `app.domain.protocols`, canonical hashing/artifacts, `RunView`, API/OpenAPI, coordinator wiring, reproducibility tools, cached artifacts, CI, and integration evidence.

## Ordered tasks

1. Task 1 — Repository foundation and agent work packets.
   - Gate A1 prerequisite for Tasks 2–3: do not begin either task until its committed public ledger is verified. Person 1 verifies only the permitted commit time, defect count, and 64-character hashes, never the private archive or labels.
2. Task 2 — Authoritative Pydantic contracts.
3. Task 3 — Canonical hashing, artifacts, and JSON schemas.
   - Gate A2 prerequisite for Task 4: do not begin Task 4 until the committed schema-bound public ledger is verified; never inspect the private archive or labels.
4. Task 4 — Protocols, configuration, safe errors, and LLM adapters.
5. Task 19 — Run store, finite-state coordinator, and public projection.
6. Task 20 — FastAPI surface, dependency wiring, and safe errors.
7. Task 21 responsibilities — cached demo, shared reproducibility scripts, CI, run evidence, and contract fixture refresh.
8. Task 25 — README, CI, reproducibility tools, package, and GitHub handoff.

## Required tests

- Test-drive every function and run focused tests, then the complete backend suite, Ruff, contract drift, replay, offline smoke, frontend checks at Gate B, and submission-package checks.
- Unit/integration tests use fakes and never call a live provider.

## Definition of done

- Public contracts are stable, generated artifacts match source, all owned tests/gates pass from documented commands, the worktree is clean at freeze points, and specialists can work without importing internals.

## Handoff evidence

- Record commits, changed interfaces/files, exact commands and outputs, contract/fixture hashes, blind first-run and Gate B evidence references, limitations, and merge order in `HANDOFF.md` and owned evidence files.
