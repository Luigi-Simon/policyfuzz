# PolicyFuzz v2 Metric milestone and Judge handoff

## Outcome

Automatically generate and execute ordinary, boundary, compound, cascading and
adversarial action sequences for one explicitly synthetic Singapore transport
reimbursement policy. Show reviewed rules, reproducible traces, independent
assertions and reduced counterexamples. Give the friend a separate Judge work
packet and branch with typed inputs/outputs and offline fixtures.

## Scope and truthfulness

Exactly four product roles remain: Metric, Orchestrator, Sandbox and Judge Agent.
The parser and runner are deterministic tools. This milestone uses rule-derived
templates, not an LLM generator. It accepts a documented controlled clause format;
unsupported or ambiguous text needs clarification and receives no scored results.
No legal or real Singapore policy claim is made. Money uses integer SGD cents.
Stateful tests simulate ordered interleavings, not concurrent infrastructure load.
The existing Sandbox fixture and v1 remain available. Live MiroFish and live Judge
are the friend's work, not claimed as complete by this milestone.

## Review and execution

The four-field policy input is sufficient to begin. Metric preparation returns
the interpreted operative rules, cited explicit goals, assumptions and an exact
review fingerprint. The user reviews these before running; edits invalidate the
review. Run submission must bind the exact four inputs and reviewed interpretation.
Never infer an authoritative goal from a generated test's expected result.

The bounded domain has submit, approve, pay and cancel actions. Approval can count
paid claims only or paid plus approved reservations. Payment can recheck allowance.
Duplicate rejection can use claim ID only or participant plus journey ID. Cancel
voids approval and releases reservations; paid claims cannot be cancelled. Repeated
payment of one claim is idempotent. Rejected actions leave state unchanged.

Independently authored, cited goals check the participant budget, one payment per
journey, no payment after cancellation, successful payment of a valid lone claim,
and rejection of amounts outside the stated range. Every case begins with explicit
state and ordered actions. Missing goals, unsupported actions and invalid state
are unscored. Empty denominators produce null. A fail needs a failed assertion;
a pass needs at least one assertion and all assertions passing.

Generation covers each of five categories and includes a combined duplicate,
interleaved approval, cancellation and retry sequence. Deletion shrinking preserves
the same failed requirement; call it action-deletion 1-minimal only after checking
every remaining single deletion. It is not a global minimum. Changing safety rules
with unchanged numeric limits must keep the generated suite stable.

## Boundaries

Keep app.v2.contracts and contracts/v2 unchanged for the existing Sandbox owner.
Add app.v2.metric_contracts and app.v2.judge_contracts as canonical shared models.
Metric endpoints are additive under /api/v2/metric. Public text remains English;
do not echo unsupported submitted prose in errors. No new dependencies or providers.
Metric results feed Judge through a typed request, along with optional validated
public Sandbox evidence. All supplied stages share run/policy identity.

Judge produces cited pros/cons, an advisory recommendation, next steps and key
interactions. Judge cannot replace deterministic test verdicts or metrics. Missing
or incomplete evidence must be exposed. Citations resolve to supplied policy
clauses, Metric cases/steps or available English Sandbox messages. Validating a
citation proves it exists, not that an LLM's interpretation is correct.

## Collaboration

Simon owns core integration, Metric, shared schemas, API and UI. The friend owns
Sandbox and Judge implementations in separate folders and feature branches.
Shared schema changes remain Simon's responsibility. Publish the Judge handoff
and create p3/feat-v2-judge from the verified shared contract checkpoint; preserve
the friend's existing Sandbox branch. Feature PRs target p1/feat-policyfuzz-v2.

## Verification

Focused failing tests before substantive implementation, deterministic edge-case
and contract validation tests, frontend review/run tests, generated schema checks,
v1 regressions and desktop/mobile browser checks. No live provider calls. Review
the complete change before publishing the core update and Judge work branch.
