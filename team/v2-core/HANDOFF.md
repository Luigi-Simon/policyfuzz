# Simon — PolicyFuzz v2 core handoff

Frontend thread view (September 11): `frontend/src/v2/SandboxEvidence.tsx` now
groups opening messages and their descendant replies into collapsible threads,
with reply counts and readable parent links. Each message keeps its original ID,
source disclosure, author and order within its thread. Multiple-parent replies
appear once under their first parent's thread and retain every parent link.
Judge citations open the containing thread and focus the exact message, including
initial fragments and repeated clicks on the same citation. No API, dependency or
backend changes were needed. Styles are in `frontend/src/v2/v2.css`; coverage is
in `frontend/src/test/v2-threads.test.tsx` and the updated `v2-app.test.tsx`.
The three new behavior tests failed before implementation; all 35 thread, fixture
and workflow tests then passed using `npm --prefix frontend run test:run --
src/test/v2-threads.test.tsx src/test/v2-app.test.tsx src/test/v2-workflow.test.tsx
--maxWorkers=1`. `npm --prefix frontend run build` and the scoped whitespace check
passed. Browser inspection on the existing Hybrid Work result verified that the
Judge comment-1 citation opens Jin Lee's three-reply thread, highlights Ravi's
reply and retains the result; captured browser warnings/errors were empty. These
are presentation checks, not a new simulation or policy evaluation.

Incident follow-up (September 11): [employment and citation verification](../../docs/v2/INCIDENT-FIXES-2026-09-11-1400.md).
The shared NumericCondition field union now includes rest_minutes, notice_days and
weekly_work_minutes; generated schemas and frontend types were updated together.
These remain partial, clause-local model checks. The real Judge adapter treats
comparison-only evidence as qualitative policy review, checks findings against
isolated citations, and performs bounded item-level repair. The native adapter
uses a five-post rotating peer feed with visible, non-destructive quality notes.
The linked record lists regression commands, acceptance evidence and limitations.

Current integration status: [assembled workflow and acceptance record](../../docs/v2/INTEGRATION.md).
Metric execution, Sandbox/Judge wiring and the combined UI/API are now implemented
on `p1/fix-v2-agent-integration`, based on main `efedfeb`. Existing canonical Sandbox
and Judge interfaces are unchanged; the new workflow API is additive. The original
milestone allocation and remaining persistence/revision work are retained below.

The user subsequently requested immediate fixes for the observed workweek run.
Those integration fixes cover the owned native wrapper, peer feed, progress and
stop handling, Judge evidence gating, Metric capability wording, and an additive
workflow health endpoint. No native MiroFish dependency/source files or teammate
worktrees were edited. Regenerated v2 Judge examples reflect the clarified Metric
limitation; v1 artifacts remain unchanged. See the linked integration record for
the new endpoint, cleanup budgets, native offline check and validation results.

The subsequent GST fixes add `PolicyConditions`, `NumericCondition`,
`EvaluateConditionAction`, `ConditionTraceStep`, Metric `partial` status and
`policy_conditions` generation in the canonical v2 Metric contract. Existing
reimbursement models and historical v1 artifacts are preserved. The prose compiler
is deterministic, bounded and source-linked; passing comparisons establish model
conformance only. Combined policy outcomes always remain unscored. Judge receives
this partial evidence and retains the closed pilot gate; the UI uses condition
outcomes rather than payment traces for this domain. V2 schemas, fixtures and
generated TS types were updated together. Job journal reconciliation now persists
terminal status safely across concurrent requests and engine restarts. See
[GST follow-up verification](../../docs/v2/GST-VOUCHER-RUN-2026-09-11.md) for the
successful live rerun and validation details. These changes remain local and uncommitted.

## Start here

Your branch: **p1/feat-v2-core**. Target pull requests at **p1/feat-policyfuzz-v2**.
Your friend works on p3/feat-v2-sandbox and p3/feat-v2-judge in separate worktrees.
Judge starts at a later shared-contract checkpoint. Preserve the existing Sandbox
branch; core owns integration of the shared types.
Read docs/v2/README.md, root AGENTS.md, and the shared Sandbox contracts before changes.

## You own

- **Orchestrator Agent:** one run lifecycle, stage progress, timeouts, integration and follow-up exploration.
- **Metric Agent:** automatic normal, boundary, compound, cascading and adversarial cases; plausibility checks and minimal counterexamples.
- **Judge integration:** shared contract, validation and app wiring. Your friend implements the adapter; see ../v2-judge/HANDOFF.md.
- Policy extraction, deterministic stateful execution, assertions and frozen regression as supporting tools.
- Four-field UI, public API, shared configuration/contracts, persistence, revisions, English public presentation and exports.

Your friend owns **Sandbox Agent**, MiroFish integration and its English output, plus **Judge Agent** in a separate folder/branch. Do not build an alternative live Sandbox implementation in their folder.

## Exact boundaries

Canonical models: app.v2.contracts (Sandbox), app.v2.metric_contracts (Metric evidence), app.v2.judge_contracts (Judge).
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
