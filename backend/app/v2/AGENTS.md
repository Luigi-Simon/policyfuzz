# V2 implementation rules

Read the root AGENTS.md and docs/v2/README.md.

- Exactly four roles: Orchestrator Agent, Metric Agent, Sandbox Agent, Judge Agent.
- Simon owns this namespace except sandbox/**.
- Import data contracts from app.v2.contracts and the adapter Protocol from app.v2.protocols.
- Do not change shared contracts independently. Update schemas, fixtures and contract checks together.
- Keep v1 schemas, public APIs and cached artifacts unchanged.
- Provider calls do not belong in deterministic evaluation, fixture adapters or tests.
- Missing expected requirements are unscored or need clarification, not invented pass/fail results.
- Do not treat a simulated stakeholder's statement as a reproduced rule violation.

