import { useRef, useState } from 'react';
import { Activity, Eye, FlaskConical } from 'lucide-react';
import type { RunView } from '../api/types';
import { HashValue } from '../components/HashValue';
import { OutcomeBadge, type OutcomeTone } from '../components/OutcomeBadge';
import { SourceCitation } from '../components/SourceCitation';
import { TraceDialog } from '../components/TraceDialog';

export interface RunEvidenceViewProps { run: RunView }

const effectStates = ['VALUE', 'GAP', 'NOT_APPLICABLE', 'CONFLICT', 'INCONCLUSIVE', 'ERROR'] as const;
const assertionStates = ['passed', 'failed', 'inconclusive', 'error'] as const;

function fraction(covered: number, total: number) {
  return total === 0 ? 'N/A' : `${covered} / ${total}`;
}

function toneForEffect(state: typeof effectStates[number]): OutcomeTone {
  if (state === 'VALUE') return 'success';
  if (state === 'NOT_APPLICABLE') return 'neutral';
  return state === 'GAP' || state === 'CONFLICT' || state === 'ERROR' ? 'danger' : 'warning';
}

export function RunEvidenceView({ run }: RunEvidenceViewProps) {
  const [traceIndex, setTraceIndex] = useState<number | null>(null);
  const traceButton = useRef<HTMLButtonElement>(null);
  const metrics = run.baseline_metrics;
  const coverage = run.coverage;
  const traces = run.traces ?? [];
  const events = run.events ?? [];
  const rejections = run.rejections ?? [];
  const artifacts = run.artifacts ?? [];
  const selectedTrace = traceIndex === null ? null : traces[traceIndex];

  return (
    <div className="content">
      <section className="page-title">
        <div><span className="eyebrow">Step 2</span><h2>Run evidence</h2><p>Measured public aggregates and visible-policy traces for this run.</p></div>
        <OutcomeBadge label={run.stage.replaceAll('_', ' ')} tone={run.error ? 'danger' : 'info'} />
      </section>

      <section className="metrics" aria-label="Measured coverage">
        {!coverage ? <p className="coverage-unavailable">Coverage counters are unavailable in this public snapshot.</p> : null}
        <article className="panel"><span className="eyebrow">Rules covered</span><div className="metric">{coverage ? fraction(coverage.covered_rules ?? 0, coverage.total_rules ?? 0) : 'N/A'}</div></article>
        <article className="panel"><span className="eyebrow">Predicate branches covered</span><div className="metric">{coverage ? fraction(coverage.covered_predicate_branches ?? 0, coverage.total_predicate_branches ?? 0) : 'N/A'}</div></article>
        <article className="panel"><span className="eyebrow">Invariants covered</span><div className="metric">{coverage ? fraction(coverage.covered_invariants ?? 0, coverage.total_invariants ?? 0) : 'N/A'}</div></article>
        <article className="panel"><span className="eyebrow">Scenarios</span><div className="metric">{coverage ? coverage.scenario_count ?? 0 : 'N/A'}</div></article>
      </section>

      {metrics ? (
        <div className="two-col">
          <section className="panel" aria-label="Effect state totals">
            <div className="section-heading"><span className="iconbox"><Activity aria-hidden="true" /></span><h3>Effect state totals</h3></div>
            <div className="aggregate-grid">{effectStates.map((state) => <div key={state}><OutcomeBadge label={state.replaceAll('_', ' ')} tone={toneForEffect(state)} /><strong>{metrics.effect_states[state] ?? 0}</strong></div>)}</div>
          </section>
          <section className="panel" aria-label="Assertion totals">
            <div className="section-heading"><span className="iconbox"><FlaskConical aria-hidden="true" /></span><h3>Assertion totals</h3></div>
            <div className="aggregate-grid">{assertionStates.map((state) => <div key={state}><OutcomeBadge label={state} tone={state === 'passed' ? 'success' : state === 'failed' || state === 'error' ? 'danger' : 'warning'} /><strong>{metrics.assertions[state] ?? 0}</strong></div>)}</div>
            <p>Pass percent: {metrics.assertion_pass_percent === null ? 'N/A' : `${metrics.assertion_pass_percent}%`}</p>
          </section>
        </div>
      ) : <section className="panel"><p>Baseline result aggregates are not available at this stage.</p></section>}

      <section className="panel">
        <h3>Public run events</h3>
        {events.length ? <ol className="event-list">
          {events.map((event, index) => <li key={`${event.timestamp}-${index}`}><time dateTime={event.timestamp}>{new Date(event.timestamp).toLocaleString()}</time><OutcomeBadge label={event.stage.replaceAll('_', ' ')} tone={event.error_id ? 'danger' : 'neutral'} /><p>{event.action_summary}</p>{event.error_id ? <code>{event.error_id}</code> : null}</li>)}
        </ol> : <p>Public run events are unavailable in this snapshot.</p>}
      </section>

      <section className="panel">
        <h3>Visible traces</h3>
        {traces.length === 0 ? <p>Trace detail is not available in the current public snapshot.</p> : (
          <div className="table-scroll" role="region" aria-label="Visible run traces" tabIndex={0}>
            <table><thead><tr><th>Scenario</th><th>Phase</th><th>Fired rules</th><th>Effect / compliance</th><th>Trace</th></tr></thead><tbody>
              {traces.map((trace, index) => <tr key={`${trace.scenario_id}-${trace.phase}`}><td><code>{trace.scenario_id}</code></td><td>{trace.phase.replaceAll('_', ' ')}</td><td>{trace.fired_rule_ids.length}</td><td>{trace.resolved_effects.length} / {trace.compliance_values.length}</td><td><button type="button" className="secondary" onClick={(event) => { traceButton.current = event.currentTarget; setTraceIndex(index); }}><Eye aria-hidden="true" size={16} /> View trace {trace.scenario_id}</button></td></tr>)}
            </tbody></table>
          </div>
        )}
      </section>

      {rejections.length ? <section className="panel"><h3>Visible rejection evidence</h3>{rejections.map((rejection) => <article className="inset" key={`${rejection.item_kind}-${rejection.item_id}`}><div className="row"><code>{rejection.item_id}</code><OutcomeBadge label={rejection.disposition.replaceAll('_', ' ')} tone="warning" /></div><p>{rejection.item_kind} · {rejection.reason_code.replaceAll('_', ' ')}</p>{rejection.source_spans.map((citation) => <SourceCitation key={citation.quote_sha256} citation={citation} />)}</article>)}</section> : null}

      {artifacts.length ? <section className="panel"><h3>Public artifacts</h3>{artifacts.map((summary) => <article className="ledger" key={summary.artifact.artifact_sha256}><div><strong>{summary.title}</strong><small>{summary.artifact.artifact_type.replaceAll('_', ' ')} · {summary.item_count ?? 'N/A'} items</small><HashValue label="Artifact hash" value={summary.artifact.artifact_sha256} /></div></article>)}</section> : null}

      {selectedTrace ? <TraceDialog trace={selectedTrace} open onClose={() => setTraceIndex(null)} returnFocusRef={traceButton} /> : null}
    </div>
  );
}
