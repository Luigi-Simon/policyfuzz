# PolicyFuzz v2 Metric and Judge Handoff Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development to execute the
> independent backend task while the controller handles shared integration.

**Goal:** Executable automatic Metric tests and a usable independent Judge handoff.
**Architecture:** Additive shared models, pure parser/generator/runner, reviewed
Metric API, English evidence UI, and a separately owned async Judge adapter port.
**Tech stack:** Existing Python/Pydantic/FastAPI and React/TypeScript/AJV/Vitest.
**Spec:** ../specs/2026-09-10-policyfuzz-v2-metric-design.md

## Global Constraints

- Preserve v1 and the existing Sandbox contracts, fixtures, hashes and owned paths.
- Exactly four agent roles; no provider calls in deterministic code or tests.
- Unsupported/unasserted cases are unscored. All scored assertions cite reviewed
  rules or explicit goals. Generation cannot author its own answer key.
- Public generated text English; original source records stay backend-only.
- Shared schemas land before teammate implementations depend on them.
- Core on p1/feat-v2-core; new Judge branch p3/feat-v2-judge; PRs target integration.

## Task 1: Metric backend

Implement additive metric_contracts.py, metric/** and focused tests. Define and
test the reviewed controlled policy format, stable automatic cases, deterministic
state transitions, independent assertions, traces and bounded deletion shrinking.
Expose prepare_policy(policy), run_metric(policy, review_fingerprint), and export
the authored sample. Return typed MetricReview and MetricRunResult. Do not edit
Orchestrator/API/frontend/Judge files. Record actual tests in the task report.

## Task 2: Shared Judge handoff and app integration

Controller owns judge_contracts.py, judge_protocols.py, offline Judge examples and
contract validation tests, generated exporters, Orchestrator/API endpoints and UI.
Reserve judge/** implementation/tests for the friend using scoped AGENTS.md.
Add review/run flow to /v2 with schema validation and clear generator/fixture labels.
Keep the existing fixture submission available. Update ownership and handoffs.

## Task 3: Review and publish

Review the backend task and whole integration. Verify schemas, focused/full tests,
lint/type/build and desktop/mobile flow. Publish checked source to core and update
its draft PR. Create the Judge branch from the shared checkpoint without changing
the existing Sandbox branch. Provide the friend exact start commands and handoff.
