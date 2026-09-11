import { SandboxEvidence } from './SandboxEvidence';
import type { Citation, WorkflowResult } from './workflow-api';

function References({ citations }: { citations: Citation[] }) {
  return <span className="v2-replies">{citations.map((ref, index) => <a key={index} href={ref.kind === 'sandbox_message' ? `#v2-message-${ref.id}` : ref.kind === 'metric_step' ? `#metric-${ref.case_id}-${ref.id}` : `#metric-${ref.id}`}>{ref.case_id ? `${ref.case_id} · ` : ''}{ref.id}</a>)}</span>;
}

export function WorkflowEvidence({ result }: { result: WorkflowResult }) {
  const { metric, judge } = result;
  return <section className="v2-evidence" aria-label="Workflow results">
    <div className="panel"><div className="row"><h2>Workflow {result.status}</h2><span className="badge">{result.execution_mode === 'live' ? 'Live agents' : 'Fixture workflow'}</span></div>
      <p>{result.policy_title}. Completion describes evidence processing, not policy readiness.</p>
      <ol className="workflow-stages">{result.stages.map(stage => <li key={stage.role}><strong>{stage.role}</strong><span className={`badge ${stage.status === 'completed' ? 'success' : 'warning'}`}>{stage.status.replaceAll('_', ' ')}</span><p>{stage.detail}</p></li>)}</ol>
      <ul>{result.limitations.map((text, i) => <li key={i}>{text}</li>)}</ul>
    </div>
    <div className="panel"><h2>Judge advice</h2>
      {judge ? <><p><span className={`badge ${judge.status === 'completed' ? '' : 'warning'}`}>{judge.status}</span> <strong>{judge.recommendation.replaceAll('_', ' ')}</strong></p>
        <p>{judge.summary}</p>
        <div className="v2-evidence-grid">{([['Pros', judge.pros], ['Cons', judge.cons]] as const).map(([title, findings]) => <section key={title}><h3>{title}</h3>{findings.length ? <ul>{findings.map((f, i) => <li key={i}><p>{f.text}</p><References citations={f.citations}/></li>)}</ul> : <p className="muted">No validated findings returned.</p>}</section>)}</div>
        {judge.next_steps.length > 0 && <><h3>Recommended next steps</h3><ol>{judge.next_steps.map((step, i) => <li key={i}><strong>{step.action}</strong><p>{step.reason}</p><References citations={step.citations}/></li>)}</ol></>}
        {judge.key_interactions.length > 0 && <><h3>Key stakeholder interactions</h3><ul>{judge.key_interactions.map((f, i) => <li key={i}><p>{f.text}</p><References citations={f.citations}/></li>)}</ul></>}
        {judge.errors.length > 0 && <div className="notice warning"><ul>{judge.errors.map((text, i) => <li key={i}>{text}</li>)}</ul></div>}
        <details><summary>Judge evidence limitations</summary><ul>{judge.limitations.map((text, i) => <li key={i}>{text}</li>)}</ul></details>
      </> : <p>Judge advice is unavailable. The retained stage evidence remains available below.</p>}
    </div>
    <div className="panel"><h2>Metric test cases</h2><p>{metric.generation_method === 'policy_scenarios' ? 'Scenario planning · no execution' : metric.cases.length ? 'Deterministic execution' : 'No executable interpretation'} · {metric.cases.length} cases · {metric.passed} passed · {metric.failed} failed · {metric.unscored} unscored</p>
      {metric.status === 'needs_clarification' && <p className="notice warning">This policy needs a supported executable interpretation. No exact pass/fail result was assigned.</p>}
      <p className="muted">Stakeholder count and test count are independent. {metric.generation_method === 'policy_scenarios' ? 'These are exploratory questions, not executed tests or verified policy findings.' : metric.generation_method === 'policy_conditions' ? 'These checks exercise explicit numeric conditions in an interpreted model. They do not verify whole-policy compliance or an independent implementation.' : metric.cases.length ? 'These cases cover a bounded reimbursement model.' : 'No executable cases were generated.'}</p>
      {metric.generation_method === 'policy_scenarios' && <p className="notice warning">Scenarios are ready for review. Executable rules and authoritative outcomes are still needed before scoring.</p>}
      {metric.status === 'partial' && metric.generation_method !== 'policy_scenarios' && <p className="notice warning">Metric ran with partial coverage. Combined policy outcomes remain unscored; inspect the limitations below.</p>}
      {metric.cases.map(c => <details className="metric-case" key={c.case_id} id={`metric-${c.case_id}`}><summary><span className={`badge ${c.verdict === 'pass' ? 'success' : 'warning'}`}>{c.verdict}</span> {c.title} · {c.category}</summary>
        <p>{c.plausibility}</p>{c.unscored_reason && <p>{c.unscored_reason}</p>}
        <ul>{c.assertions.map(a => <li key={a.requirement_id}><a href={`#metric-${a.requirement_id}`}>{a.requirement_id}</a>: {a.passed ? 'Pass' : 'Fail'}. {a.expected} {a.actual}</li>)}</ul>
        <ol>{c.trace.map(step => <li id={`metric-${c.case_id}-${step.step_id}`} key={step.step_id}><strong>{'matches' in step ? `Condition check · ${step.matches ? 'matches condition' : 'does not match condition'}` : `${step.action.action} · ${step.accepted ? 'accepted' : 'rejected'}`}</strong><p>{step.detail}{'participant_paid_cents_before' in step && <> Participant paid: {step.participant_paid_cents_before} → {step.participant_paid_cents_after} SGD cents.</>}</p></li>)}</ol>
        {c.minimal_actions && <p>Failure reproduced after reducing to {c.minimal_actions.length} actions: {c.minimal_actions.map(a => a.action).join(' → ')}.</p>}
      </details>)}
      <details><summary>Policy interpretation, goals and limitations</summary><ul>{[...metric.review.clauses, ...metric.review.goals].map(c => <li key={c.id} id={`metric-${c.id}`}><strong>{c.id}</strong> {c.text}</li>)}</ul><ul>{[...metric.review.assumptions, ...metric.limitations].map((text, i) => <li key={i}>{text}</li>)}</ul></details>
    </div>
    {result.sandbox && <SandboxEvidence result={result.sandbox}/>}
    <details className="panel v2-trace"><summary>Workflow identity</summary><p>Run: <code>{result.run_id}</code></p><p>Exact policy SHA-256: <code>{result.policy_text_sha256}</code></p><p>Test suite SHA-256: <code>{metric.suite_sha256}</code></p></details>
  </section>;
}
