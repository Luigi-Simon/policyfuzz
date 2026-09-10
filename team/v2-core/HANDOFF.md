# Simon — PolicyFuzz v2 core handoff

## Start here

Your branch: **p1/feat-v2-core**. Target pull requests at **p1/feat-policyfuzz-v2**.
Your friend works on p3/feat-v2-sandbox. Both begin at the same foundation commit.
Read docs/v2/README.md, root AGENTS.md, and the shared Sandbox contracts before changes.

## You own

- **Orchestrator Agent:** one run lifecycle, stage progress, timeouts, integration and follow-up exploration.
- **Metric Agent:** automatic normal, boundary, compound, cascading and adversarial cases; plausibility checks and minimal counterexamples.
- **Judge Agent:** evidence-grounded pros/cons, recommendations/next steps, key interactions and test results.
- Policy extraction, deterministic stateful execution, assertions and frozen regression as supporting tools.
- Four-field UI, public API, shared configuration/contracts, persistence, revisions, English public presentation and exports.

Your friend owns **Sandbox Agent**, MiroFish integration and its English output. Do not build an alternative live Sandbox implementation in their folder.

## Exact boundaries

Canonical models: app.v2.contracts.
Canonical protocol: app.v2.protocols.SandboxService.
Your fixture: app.v2.fixtures.FixtureSandboxService.
Friend implementation target: app.v2.sandbox.service.MiroFishSandboxService (not implemented by this foundation).
The Orchestrator consumes the protocol, not a MiroFish-specific transport.

Own backend/app/v2/** except sandbox/**; backend/tests/v2/** except sandbox/**;
contracts/v2; and v2 additions to the frontend, APIs, docs and shared configuration.
This does not transfer ownership of preserved v1 features. Any integration change
affecting an existing v1 surface must preserve its behaviour and include relevant
regression verification. Update generated contracts and both handoffs together if
the interface changes, merge that focused change into the integration branch first,
and have both feature branches merge integration before depending on it.

## First implementation steps

The approved first core milestone implements step 2 with a stateless fixture API
and the `/v2` evidence screen. See [the first-run handoff](../../docs/v2/FIRST-RUN.md)
for startup, interfaces and remaining work. Steps 3–7 remain separate milestones.

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
