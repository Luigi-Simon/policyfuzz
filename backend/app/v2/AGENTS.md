# V2 implementation rules

Read the root AGENTS.md and docs/v2/README.md.

- Exactly four roles: Orchestrator Agent, Metric Agent, Sandbox Agent, Judge Agent.
- Simon owns this namespace except sandbox/** and judge/**.
- Import Sandbox contracts/protocol from app.v2.contracts and app.v2.protocols. Additive Metric and Judge contracts come from app.v2.metric_contracts and app.v2.judge_contracts; JudgeService comes from app.v2.judge_protocols.
- Do not change shared contracts independently. Update schemas, fixtures and contract checks together.
- Keep v1 schemas, public APIs and cached artifacts unchanged.
- Provider calls do not belong in deterministic evaluation, fixture adapters or tests.
- Missing expected requirements are unscored or need clarification, not invented pass/fail results.
- Do not treat a simulated stakeholder's statement as a reproduced rule violation.

