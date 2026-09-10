# Metric Agent milestone

Start the existing v2 launcher with `npm run dev:v2`, then open
http://127.0.0.1:5173/v2. Backend dependencies and frontend setup are in README.md.
This milestone requires no provider key.

1. Load the transport claims example into the four policy fields.
2. Select **Review policy rules** and inspect operative clauses, explicit goals,
   interpreted amounts, assumptions and limitations.
3. Select **Confirm rules and run tests**. The runner executes automatically
   generated action sequences and shows pass/fail/unscored results.
4. Expand a failed case to inspect its exact actions, assertion and trace. The
   reduced sequence preserves the failed requirement using action deletion.

The sample is a fictional Singapore organisation's proposed transport reimbursement
policy in SGD. It is not a real government policy, legal interpretation or report
about an actual incident. Its weak approval and duplicate clauses intentionally
demonstrate reproduced policy-goal failures.

## What is implemented

Metric uses deterministic rule-derived templates parameterized by reviewed rules.
It covers normal, boundary, compound, cascading and adversarial cases, including
interleaved approvals, duplicate journeys, cancellation and payment retries.
Money is integer cents. Tests simulate ordered state transitions; they do not
run simultaneous requests against a real payment system or measure real traffic.

The parser accepts the documented controlled format in the sample, including
explicit goals. Unknown, missing, conflicting or extra clauses require clarification.
It does not guess a general natural-language policy interpretation. Review binds
all four inputs and the parsed interpretation; changing any input requires review.
The personality seed and stakeholder count do not change deterministic case count.

Assertions come from reviewed explicit goals and operative amount constraints.
No assertions or unsupported execution means unscored. Pass rate describes only
the executed scored cases; it is not the probability a policy will succeed. Passing
this bounded suite does not establish that a policy is generally correct or safe.

The app still offers the original Sandbox fixture preview separately. Its authored
dialogue does not analyse the claims policy. Live MiroFish, the friend's Judge
adapter, Judge API/UI execution, persistent runs and the policy revision workflow
remain subsequent integration work. The core Judge port is implemented and tested
with a fake adapter. Judge's independent adapter handoff is ready in
team/v2-judge/HANDOFF.md.

## Additive interfaces

| Endpoint | Input | Output |
| --- | --- | --- |
| GET /api/v2/metric/sample | none | Four-field synthetic policy |
| POST /api/v2/metric/prepare | policy | MetricReview |
| POST /api/v2/metric/runs | policy, review_fingerprint | MetricRunResult |

A stale review receives HTTP 409. Unsupported prose returns needs_clarification
with no scored cases. Error responses contain fixed English messages. These
stateless endpoints do not persist submissions. The existing /api/v2/runs
Sandbox-only fixture endpoint remains available.

Shared sources: app.v2.metric_contracts, app.v2.judge_contracts and
app.v2.judge_protocols. Existing app.v2.contracts and contracts/v2 stay unchanged.
Generated API schema is contracts/v2-app; Judge examples are contracts/v2-judge.

## Connect the friend's Judge adapter

After producing a MetricRunResult, core calls
`request = orchestrator.prepare_judge(policy, metric, sandbox=None)`, then
`result = await orchestrator.judge(request, judge_service)` with the friend's
`JudgeService` implementation. Core checks that the reviewed inputs still match
the Metric evidence, supplies a separate validated request snapshot, bounds the
adapter call with a timeout, and validates the returned evidence references and
run identity. Failures return safe errors; they do not substitute example reports.

A Metric-only request explicitly records missing Sandbox evidence. The shared
Judge contract requires incomplete evidence to remain partial (or failed), so it
cannot become a completed evaluation. To combine stages, core must first supply
policy-specific public Sandbox evidence with the same run ID, policy version and
policy-text hash. The separate preview endpoint creates its own fixture run and
is not a source of evidence to append to an unrelated Metric run.

The default sample currently produces 12 executed cases: 9 pass and 3 fail.
The failures reproduce excess payouts and duplicate journey payments against
the policy's explicit goals. These counts describe this sample only.

## Verify offline

```bash
backend/.venv/bin/python -m pytest backend/tests/v2 -q
PYTHONPATH=backend backend/.venv/bin/python -m app.v2.export_api --check
PYTHONPATH=backend backend/.venv/bin/python -m app.v2.export_judge --check
npm --prefix frontend run check:generated
npm --prefix frontend run test:run
npm --prefix frontend run build
```

Canonical sample text is returned by the sample endpoint and defined in
backend/app/v2/metric/sample.py. The same suite is generated when safety flags
change while numeric limits remain the same. This is a deterministic comparison
property, not a completed persisted revision/approval workflow.
