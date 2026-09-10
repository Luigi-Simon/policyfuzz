# Simon — PolicyFuzz v2 core handoff

## Start here

Your branch: **p1/feat-v2-core**. Target pull requests at **p1/feat-policyfuzz-v2**.
Your friend works on p3/feat-v2-sandbox and p3/feat-v2-judge in separate worktrees.
The Judge branch includes the later shared contract checkpoint; do not reset
either friend branch.
Read docs/v2/README.md, root AGENTS.md, and the shared Sandbox contracts before changes.

## You own

- **Orchestrator Agent:** one run lifecycle, stage progress, timeouts, integration and follow-up exploration.
- **Metric Agent:** automatic normal, boundary, compound, cascading and adversarial cases; plausibility checks and minimal counterexamples.
- **Judge integration:** shared evidence contract and validation, API/UI wiring. The friend implements the Judge adapter; see ../v2-judge/HANDOFF.md.
- Policy extraction, deterministic stateful execution, assertions and frozen regression as supporting tools.
- Four-field UI, public API, shared configuration/contracts, persistence, revisions, English public presentation and exports.

Your friend owns **Sandbox Agent**, MiroFish integration and its English output, plus the separate **Judge Agent** adapter. Do not build an alternative live Sandbox implementation in their folder.

## Exact boundaries

Canonical models: app.v2.contracts (Sandbox), app.v2.metric_contracts (Metric), app.v2.judge_contracts (Judge).
Canonical protocol: app.v2.protocols.SandboxService.
Your fixture: app.v2.fixtures.FixtureSandboxService.
Friend implementation target: app.v2.sandbox.service.MiroFishSandboxService (not implemented by this foundation).
The Orchestrator consumes the protocol, not a MiroFish-specific transport.

Own backend/app/v2/** except sandbox/** and judge/**; backend/tests/v2/** except sandbox/** and judge/**;
contracts/v2; and v2 additions to the frontend, APIs, docs and shared configuration.
This does not transfer ownership of preserved v1 features. Any integration change
affecting an existing v1 surface must preserve its behaviour and include relevant
regression verification. Update generated contracts and both handoffs together if
the interface changes, merge that focused change into the integration branch first,
and have both feature branches merge integration before depending on it.

## Current milestone

Metric review/execution, the Judge shared handoff and core's validated Judge port
are now added. Read
[the Metric run guide](../../docs/v2/METRIC-RUN.md) and
[the Judge handoff](../v2-judge/HANDOFF.md). The friend implements Judge; core owns
integration. `Orchestrator.prepare_judge(policy, metric, sandbox=None)` binds the
reviewed policy to actual Metric evidence; `await Orchestrator.judge(request,
service)` calls the friend's injected adapter with a timeout and validates its
result. Missing Sandbox evidence remains explicit. No Judge adapter or Judge
API/UI execution is included yet. Existing Sandbox contracts remain unchanged.

The shared Metric state-counter bound now allows 6,400,000,000 cents (64 bounded
claims) so the runner can represent and report overspending above the policy's
allowance. This widens a validation bound; field names and the Judge port are
unchanged. Judge consumers should use the regenerated shared models and schemas
when integrating the core branch.

## Original implementation sequence

The approved first core milestone implements step 2 with a stateless fixture API
and the `/v2` evidence screen. See [the first-run handoff](../../docs/v2/FIRST-RUN.md)
for startup and the original interfaces. This Metric milestone implements steps
3–4 and the shared integration port for step 5; the friend's report implementation
and steps 6–7 remain work to integrate.

1. Run the foundation smoke command described in docs/v2/README.md.
2. Build one run from the four user fields and call the fixture through SandboxService. Label every fixture result.
3. Implement supported state/actions for one demo domain; cases must have an initial state and ordered actions.
4. Add automatic Metric generation. Derive scored assertions from cited reviewed rules or explicit goals; never let a generated outcome become its own answer key.
5. Add Judge reporting with exact test and Sandbox message references.
6. Persist a real revised policy text and linked rules; retest the frozen suite without silently changing assertions.
7. Replace the fixture with the friend's implementation through dependency injection, then run integration checks.

Do not send expected verdicts or historical outcomes into stakeholder seed material.
Validate the returned request/run/version fingerprint before accepting evidence.
A simulated policy violation is not automatically a policy defect.
Unsupported or unasserted cases are not scored passes.
Handle partial, failed and cancelled Sandbox results separately from completed results.

## Naming

Exactly four active v2 roles:
- Orchestrator Agent
- Metric Agent
- Sandbox Agent
- Judge Agent

Fuzz Agent is renamed to Metric Agent in the v2 contract and active documentation.
Keep PolicyFuzz as the project name.
Any later migration of legacy fuzzing module paths must update imports, configuration, tests and documentation in one change. Do not alter archived fixture hashes merely to change a label.

## Done for this first core milestone

One four-field submission calls SandboxService through the Orchestrator and
displays validated English public evidence with exact message references.
Fixture mode is explicit; complete and partial evidence remain distinct.
No durable storage or Judge evaluation is included in this milestone. Existing
v1 functionality remains available through its original entry and launcher.

## What to include in your handoff

Record the exact commit and base, changed files, public interface/schema changes,
dependency/configuration changes, commands and their actual results, fixture or
live execution evidence, submission evidence if any, and remaining limitations.
Do not describe a fixture check as a real simulation or a full-app acceptance test.
