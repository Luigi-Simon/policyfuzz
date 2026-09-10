import { AlertTriangle, CheckCircle2, CircleHelp, FlaskConical, ListChecks, ShieldCheck, XCircle } from 'lucide-react';
import type { MetricAction, MetricReview, MetricRunResult } from './metric-api';

function money(cents: number): string {
  return `SGD ${(cents / 100).toFixed(2)}`;
}

function titleCase(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, character => character.toUpperCase());
}

function actionLabel(action: MetricAction): string {
  if (action.action === 'submit' && 'participant_id' in action) {
    return `Submit ${action.claim_id} · ${action.participant_id} · ${action.journey_id} · ${money(action.amount_cents)}`;
  }
  if (['approve', 'pay', 'cancel'].includes(action.action) && 'claim_id' in action) {
    return `${titleCase(action.action)} ${action.claim_id}`;
  }
  return `${titleCase(action.action)}${'parameters' in action && action.parameters.length > 0 ? ` · ${action.parameters.join(', ')}` : ''}`;
}

export function MetricReviewPanel({ review, busy, onRun }: {
  review: MetricReview;
  busy: boolean;
  onRun: () => void;
}) {
  const ready = review.status === 'ready' && review.rules !== null;
  return <section className="panel v2-metric-review" aria-labelledby="metric-review-title">
    <div className="row">
      <div><p className="eyebrow">METRIC INTERPRETATION</p><h2 id="metric-review-title">Metric rule review</h2></div>
      <span className={`badge ${ready ? 'success' : 'warning'}`}>{ready ? 'Ready to run' : 'Needs clarification'}</span>
    </div>
    <p className="muted">Review the deterministic interpretation before accepting its goals and assumptions. This covers one synthetic Singapore transport claims domain.</p>
    {!ready && <div className="notice warning v2-metric-notice"><AlertTriangle size={20} aria-hidden="true"/><div><strong>Needs clarification</strong><p>The Metric cannot score this prose. Clarify the policy rules, then review again.</p></div></div>}
    <div className="v2-review-grid">
      <div>
        <h3>Interpreted clauses</h3>
        {review.clauses.length === 0 ? <p className="muted">No supported clauses were identified.</p> :
          <ol className="v2-clause-list">{review.clauses.map(clause => <li key={clause.id}><code>{clause.id}</code><span>{clause.text}</span></li>)}</ol>}
      </div>
      <div>
        <h3>Test goals</h3>
        {review.goals.length === 0 ? <p className="muted">No executable goals were identified.</p> :
          <ol className="v2-goal-list">{review.goals.map(goal => <li key={goal.id}><div><code>{goal.id}</code><span>{goal.text}</span></div><small className="muted">Clauses: {goal.clause_ids.join(', ')}</small></li>)}</ol>}
      </div>
    </div>
    {review.rules && <dl className="v2-rule-grid">
      <div><dt>Per-claim limit</dt><dd>{money(review.rules.per_claim_limit_cents)}</dd></div>
      <div><dt>Participant allowance</dt><dd>{money(review.rules.participant_allowance_cents)}</dd></div>
      <div><dt>Approval accounting</dt><dd>{review.rules.approval_budget_accounting === 'paid_only' ? 'Paid claims only' : 'Paid and approved claims'}</dd></div>
      <div><dt>Payment budget recheck</dt><dd>{review.rules.payment_budget_recheck ? 'Required' : 'Not required'}</dd></div>
      <div><dt>Duplicate scope</dt><dd>{review.rules.duplicate_scope === 'claim_id' ? 'Claim ID' : 'Journey'}</dd></div>
    </dl>}
    <div className="v2-notes-grid">
      <div><h3>Assumptions</h3>{review.assumptions.length ? <ul>{review.assumptions.map((note, index) => <li key={index}>{note}</li>)}</ul> : <p className="muted">None stated.</p>}</div>
      <div><h3>Limitations</h3>{review.limitations.length ? <ul>{review.limitations.map((note, index) => <li key={index}>{note}</li>)}</ul> : <p className="muted">None stated.</p>}</div>
    </div>
    <details className="v2-provenance"><summary>Review provenance</summary><dl>
      <div><dt>Policy SHA-256</dt><dd><code>{review.policy_text_sha256}</code></dd></div>
      <div><dt>Review fingerprint</dt><dd><code>{review.review_fingerprint}</code></dd></div>
    </dl></details>
    {ready && <div className="actions v2-confirm"><span className="muted small">Clicking confirms the goals, assumptions, and limitations shown above.</span><button type="button" className="primary" disabled={busy} onClick={onRun}>{busy ? 'Running Metric tests…' : 'Confirm rules and run tests'}</button></div>}
  </section>;
}

function VerdictIcon({ verdict }: { verdict: 'pass' | 'fail' | 'unscored' }) {
  return verdict === 'pass' ? <CheckCircle2 aria-hidden="true"/> : verdict === 'fail' ? <XCircle aria-hidden="true"/> : <CircleHelp aria-hidden="true"/>;
}

export function MetricEvidence({ result }: { result: MetricRunResult }) {
  const openTrace = (caseId: string) => {
    const trace = document.getElementById(`metric-trace-${caseId}`);
    if (trace instanceof HTMLDetailsElement) trace.open = true;
  };
  const passRate = result.pass_rate === null ? 'Not scored' : `${Math.round(result.pass_rate * 100)}%`;
  return <section className="v2-metric-results" aria-labelledby="metric-results-title">
    <div className="panel">
      <div className="row"><div><p className="eyebrow">DETERMINISTIC METRIC RUN</p><h2 id="metric-results-title">Metric test results</h2></div>
        <div className="badge-row"><span className="badge"><FlaskConical size={13} aria-hidden="true"/>Rule-derived templates</span><span className="badge success">{titleCase(result.status)}</span></div></div>
      <p className="muted">Tests are generated from confirmed rules for one supported synthetic Singapore transport claims domain.</p>
      <dl className="v2-metric-counts">
        <div className="pass"><dt>Passed</dt><dd>{result.passed}</dd></div>
        <div className="fail"><dt>Failed</dt><dd>{result.failed}</dd></div>
        <div className="unscored"><dt>Unscored</dt><dd>{result.unscored}</dd></div>
        <div><dt>Pass rate</dt><dd>{passRate}</dd></div>
      </dl>
      <p className="small muted">Tested cases only; this is not the chance that a policy succeeds.</p>
      <p className="small muted">Stakeholder count controls Sandbox participants, independently of Metric test cases.</p>
      {result.limitations.length > 0 && <div className="notice neutral v2-metric-notice"><ShieldCheck size={20} aria-hidden="true"/><div><strong>Run limitations</strong><ul>{result.limitations.map((note, index) => <li key={index}>{note}</li>)}</ul></div></div>}
    </div>
    <div className="v2-case-list">
      {result.cases.map((item, index) => <article className={`panel v2-case verdict-${item.verdict}`} key={item.case_id}>
        <div className="row v2-case-heading"><div className="v2-verdict"><VerdictIcon verdict={item.verdict}/><div><p className="eyebrow">CASE {index + 1} · {item.case_id}</p><h3>{item.title}</h3></div></div>
          <div className="badge-row"><span className="badge">{titleCase(item.category)}</span><span className={`badge ${item.verdict === 'pass' ? 'success' : item.verdict === 'fail' ? 'danger' : 'warning'}`}>{titleCase(item.verdict)}</span></div></div>
        <p><strong>Why plausible:</strong> {item.plausibility}</p>
        {item.unscored_reason && <div className="notice warning"><CircleHelp size={19} aria-hidden="true"/><div><strong>Unscored</strong><p>{item.unscored_reason}</p></div></div>}
        <details open={index === 0}><summary>Ordered actions · {item.actions.length}</summary><ol className="v2-action-list">{item.actions.map((action, actionIndex) => <li key={actionIndex}><code>{actionIndex + 1}</code><span>{actionLabel(action)}</span></li>)}</ol></details>
        <details><summary>Initial state · {item.initial_state.claims.length} claims, {item.initial_state.participants.length} participants</summary>
          {item.initial_state.claims.length === 0 && item.initial_state.participants.length === 0 ? <p className="small muted">Empty initial state.</p> : <div className="v2-state-grid">
            <div><h4>Claims</h4><ul>{item.initial_state.claims.map(claim => <li key={claim.claim_id}><code>{claim.claim_id}</code> · {claim.status} · participant <code>{claim.participant_id}</code> · journey <code>{claim.journey_id}</code> · {money(claim.amount_cents)}</li>)}</ul></div>
            <div><h4>Participants</h4><ul>{item.initial_state.participants.map(person => <li key={person.participant_id}><code>{person.participant_id}</code> · paid {money(person.paid_cents)} · reserved {money(person.reserved_cents)}</li>)}</ul></div>
          </div>}
        </details>
        <details id={`metric-trace-${item.case_id}`}><summary>Execution trace · {item.trace.length} steps</summary>
          {item.trace.length === 0 ? <p className="small muted">No supported execution steps were produced.</p> : <ol className="v2-trace-list">{item.trace.map(step => <li id={`metric-${item.case_id}-${step.step_id}`} key={step.step_id}>
            <div className="row"><strong>{step.step_id} · action {step.action_index + 1}</strong><span className={`badge ${step.accepted ? 'success' : 'danger'}`}>{step.accepted ? 'Accepted' : 'Rejected'}</span></div>
            <p>{actionLabel(step.action)}</p><p>{step.detail}</p>
            <dl><div><dt>Paid</dt><dd>{money(step.participant_paid_cents_before)} → {money(step.participant_paid_cents_after)}</dd></div><div><dt>Reserved</dt><dd>{money(step.participant_reserved_cents_before)} → {money(step.participant_reserved_cents_after)}</dd></div></dl>
            <details><summary>State hashes</summary><code>{step.before_state_sha256}</code><span aria-hidden="true"> → </span><code>{step.after_state_sha256}</code></details>
          </li>)}</ol>}
        </details>
        <details><summary>Goal assertions · {item.assertions.length}</summary>
          {item.assertions.length === 0 ? <p className="small muted">No scored assertions.</p> : <ul className="v2-assertion-list">{item.assertions.map(assertion => <li key={assertion.requirement_id}>
            <div className="row"><strong><ListChecks size={16} aria-hidden="true"/>{assertion.requirement_id}</strong><span className={`badge ${assertion.passed ? 'success' : 'danger'}`}>{assertion.passed ? 'Met' : 'Not met'}</span></div>
            <p><strong>Expected:</strong> {assertion.expected}</p><p><strong>Actual:</strong> {assertion.actual}</p>
            <p className="small muted">Trace: {assertion.step_refs.map(step => <a key={step} href={`#metric-${item.case_id}-${step}`} onClick={() => openTrace(item.case_id)}>{step}</a>).reduce<React.ReactNode[]>((nodes, link, linkIndex) => [...nodes, linkIndex ? ', ' : '', link], [])}</p>
          </li>)}</ul>}
        </details>
        {item.verdict === 'fail' && item.minimal_actions && <details><summary>Action-deletion reduction</summary><p className="small muted">A sequence produced by deleting actions. It may be the same length as the original; no global minimality is claimed.</p><ol className="v2-action-list">{item.minimal_actions.map((action, actionIndex) => <li key={actionIndex}><code>{actionIndex + 1}</code><span>{actionLabel(action)}</span></li>)}</ol></details>}
      </article>)}
    </div>
    <details className="panel v2-provenance"><summary>Metric provenance and bindings</summary><dl>
      {Object.entries({ 'Run ID': result.run_id, 'Policy version': result.policy_version, 'Schema version': result.schema_version, 'Generation method': result.generation_method, 'Policy SHA-256': result.policy_text_sha256, 'Review fingerprint': result.review_fingerprint, 'Suite SHA-256': result.suite_sha256 }).map(([label, value]) => <div key={label}><dt>{label}</dt><dd><code>{value}</code></dd></div>)}
    </dl></details>
  </section>;
}
