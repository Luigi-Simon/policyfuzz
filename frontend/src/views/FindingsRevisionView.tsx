import { useState } from 'react';
import { AlertTriangle, Check, Code2 } from 'lucide-react';
import type { ConfirmRevisionRequest, FindingDecision, RuleSummary, RunView, SelectFindingsRequest, components } from '../api/types';
import { OutcomeBadge } from '../components/OutcomeBadge';
import { SourceCitation } from '../components/SourceCitation';

export interface FindingsRevisionViewProps {
  run: RunView;
  busy: boolean;
  onSelect: (request: SelectFindingsRequest) => void;
  onConfirm: (request: ConfirmRevisionRequest) => void;
}

type DecisionValue = FindingDecision['decision'] | '';
type Severity = NonNullable<FindingDecision['reviewer_severity']>;
type RevisionRuleDraft = components['schemas']['RevisionRuleDraft'];
type RuleSemantics = Pick<RuleSummary, 'description' | 'when' | 'effects' | 'overrides'>;

function printable(value: unknown) {
  return Array.isArray(value) ? value.join(', ') : String(value);
}

function PredicateList({ predicates }: { predicates: RuleSemantics['when'] }) {
  return predicates.length ? predicates.map((predicate, index) => <code key={index}>{predicate.field} {predicate.operator} {printable(predicate.value)}</code>) : <code>Always</code>;
}

function OverrideList({ overrides }: { overrides: RuleSemantics['overrides'] }) {
  return (overrides ?? []).length ? <>{(overrides ?? []).map((override, index) => <code key={`${override.dimension}-${override.target_rule_id}-${index}`}>{override.dimension.replaceAll('_', ' ')} → {override.target_rule_id}</code>)}</> : <code>None</code>;
}

function RuleSemanticsBlock({ rule }: { rule: RuleSemantics }) {
  return <><p>{rule.description}</p><div className="logic"><div><span className="eyebrow">When</span><PredicateList predicates={rule.when} /></div><div><span className="eyebrow">Effects</span>{rule.effects.map((effect, index) => <code key={index}>{effect.dimension.replaceAll('_', ' ')} = {effect.value}</code>)}</div><div><span className="eyebrow">Overrides</span><OverrideList overrides={rule.overrides} /></div></div></>;
}

function RuleBlock({ label, rule }: { label: string; rule: RuleSummary | null | undefined }) {
  return (
    <div>
      <span className="eyebrow">{label}</span>
      {!rule ? <p>None</p> : <div className="rule-summary"><h4>{rule.rule_id} · revision {rule.revision}</h4><RuleSemanticsBlock rule={rule} />{rule.confidence_percent === null ? <p className="muted">Extraction confidence: unavailable</p> : <p className="muted">Extraction confidence: {rule.confidence_percent}% · display only</p>}{rule.citations.map((citation) => <SourceCitation key={citation.citation_id} citation={citation.span} />)}</div>}
    </div>
  );
}

function DraftBlock({ label, rule }: { label: string; rule: RevisionRuleDraft }) {
  return <div><span className="eyebrow">{label}</span><div className="rule-summary"><RuleSemanticsBlock rule={rule} /></div></div>;
}

export function FindingsRevisionView({ run, busy, onSelect, onConfirm }: FindingsRevisionViewProps) {
  const [decisions, setDecisions] = useState<Record<string, DecisionValue>>({});
  const [severities, setSeverities] = useState<Record<string, Severity | ''>>({});
  const [message, setMessage] = useState('');
  const findingsPending = run.pending_confirmation?.kind === 'findings' ? run.pending_confirmation : null;
  const revisionPending = run.pending_confirmation?.kind === 'revision' ? run.pending_confirmation : null;
  const pendingIds = new Set(findingsPending?.finding_ids ?? []);
  const findings = run.findings ?? [];
  const allowedActions = run.allowed_actions ?? [];

  const submitFindings = () => {
    if (!findingsPending) return;
    setMessage('');
    for (const findingId of findingsPending.finding_ids) {
      const finding = findings.find((item) => item.finding_id === findingId);
      if (!finding || !decisions[findingId]) return setMessage(`Choose accept or reject for ${findingId}.`);
      const needsSeverity = decisions[findingId] === 'accept' && finding.severity === null && (finding.finding_type === 'structural_gap' || finding.finding_type === 'conflict');
      if (needsSeverity && !severities[findingId]) return setMessage(`Choose reviewer severity for ${findingId}.`);
    }
    onSelect({
      schema_version: '1.0',
      decisions: findingsPending.finding_ids.map((finding_id) => ({
        schema_version: '1.0',
        finding_id,
        decision: decisions[finding_id] as FindingDecision['decision'],
        reviewer_severity: decisions[finding_id] === 'accept' && findings.find((item) => item.finding_id === finding_id)?.severity === null
          && ['structural_gap', 'conflict'].includes(findings.find((item) => item.finding_id === finding_id)?.finding_type ?? '')
          ? severities[finding_id] || null
          : null,
      })),
    });
  };

  return (
    <div className="content">
      <section className="page-title">
        <div><span className="eyebrow">Step 3</span><h2>Findings &amp; revision</h2><p>Review deterministic findings and the server-proposed typed revision.</p></div>
        <OutcomeBadge label={run.stage.replaceAll('_', ' ')} tone="info" />
      </section>

      <section className="panel">
        <div className="section-heading"><span className="iconbox"><AlertTriangle aria-hidden="true" /></span><div><span className="eyebrow">Public finding summaries</span><h3>{findings.length} findings</h3></div></div>
        <div className="finding-list">
          {findings.length === 0 ? <p>No finding summaries are available in this public snapshot.</p> : findings.map((finding) => {
            const reviewable = pendingIds.has(finding.finding_id);
            const needsSeverity = decisions[finding.finding_id] === 'accept' && finding.severity === null && (finding.finding_type === 'structural_gap' || finding.finding_type === 'conflict');
            return (
              <fieldset className={`finding-card ${reviewable ? '' : 'candidate'}`} key={finding.finding_id} aria-label={`Review ${finding.finding_id}`} aria-disabled={!reviewable}>
                <legend>{finding.finding_id}</legend>
                <div className="row"><div className="badge-row"><OutcomeBadge label={finding.finding_type.replaceAll('_', ' ')} tone={finding.finding_type === 'conflict' || finding.finding_type === 'structural_gap' ? 'danger' : 'warning'} /><OutcomeBadge label={finding.dimension.replaceAll('_', ' ')} tone="info" /><OutcomeBadge label={finding.review_status} /></div><strong>{finding.witness_count} witness{finding.witness_count === 1 ? '' : 'es'}</strong></div>
                <p>{finding.summary}</p>
                <p>Severity: {finding.severity ?? 'not assigned by the engine'}</p>
                {reviewable ? <div className="decision-bar"><div className="segmented" role="radiogroup" aria-label={`Decision for ${finding.finding_id}`}><label><input type="radio" name={`decision-${finding.finding_id}`} checked={decisions[finding.finding_id] === 'accept'} disabled={busy} onChange={() => setDecisions((current) => ({ ...current, [finding.finding_id]: 'accept' }))} /> Accept</label><label><input type="radio" name={`decision-${finding.finding_id}`} checked={decisions[finding.finding_id] === 'reject'} disabled={busy} onChange={() => setDecisions((current) => ({ ...current, [finding.finding_id]: 'reject' }))} /> Reject</label></div>{needsSeverity ? <label>Reviewer severity<select aria-label={`Reviewer severity for ${finding.finding_id}`} value={severities[finding.finding_id] ?? ''} disabled={busy} onChange={(event) => setSeverities((current) => ({ ...current, [finding.finding_id]: event.target.value as Severity }))}><option value="">Choose severity</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select></label> : null}</div> : <p className="muted">Read-only — this ID is outside the pending finding confirmation.</p>}
              </fieldset>
            );
          })}
        </div>
        {findingsPending ? <div className="actions">{message ? <p role="alert" className="form-error">{message}</p> : null}<button type="button" disabled={busy || !allowedActions.includes('select_findings')} onClick={submitFindings}><Check aria-hidden="true" size={17} /> Submit finding decisions</button></div> : null}
      </section>

      {revisionPending ? <section className="panel">
        <div className="section-heading"><span className="iconbox"><Code2 aria-hidden="true" /></span><div><span className="eyebrow">Proposal {revisionPending.proposal_id}</span><h3>Typed revision operations</h3></div></div>
        <div className="operation-list">{revisionPending.operations.map((summary, index) => {
          const operation = summary.operation;
          const mergedAfter = operation.kind === 'add_override' && summary.before ? {
            ...summary.before,
            overrides: [...(summary.before.overrides ?? []), { schema_version: '1.0' as const, dimension: operation.dimension, target_rule_id: operation.target_rule_id }],
          } : null;
          return <article className="diff" role="group" aria-label={`${operation.kind.replaceAll('_', ' ')} ${operation.rule_id}`} key={`${operation.kind}-${operation.rule_id}-${index}`}><div className="row"><OutcomeBadge label={operation.kind.replaceAll('_', ' ')} tone="info" /><code>{operation.rule_id}</code></div><p>Addresses: {operation.finding_ids.join(', ')}</p>{operation.kind === 'replace_rule' ? <p>Expected baseline revision: {operation.expected_revision}</p> : null}{operation.kind === 'add_override' ? <div className="two-col"><RuleBlock label="Before" rule={summary.before} /><RuleBlock label="After" rule={mergedAfter} /></div> : <div className="two-col"><RuleBlock label="Before" rule={summary.before} />{operation.kind === 'add_rule' || operation.kind === 'replace_rule' ? <DraftBlock label="After" rule={operation.rule} /> : null}</div>}</article>;
        })}</div>
        <div className="notice warning wording"><AlertTriangle aria-hidden="true" /><div><strong>Unverified wording suggestion — not what was tested.</strong><blockquote>{revisionPending.draft_policy_wording}</blockquote></div></div>
        <div className="actions"><button type="button" className="danger" disabled={busy || !allowedActions.includes('reject_revision')} onClick={() => onConfirm({ schema_version: '1.0', proposal_id: revisionPending.proposal_id, decision: 'reject' })}>Reject revision</button><button type="button" disabled={busy || !allowedActions.includes('confirm_revision')} onClick={() => onConfirm({ schema_version: '1.0', proposal_id: revisionPending.proposal_id, decision: 'confirm' })}>Confirm revision</button></div>
      </section> : <section className="panel"><h3>Revision proposal</h3><p>Typed revision operations are unavailable in the current public snapshot.</p></section>}
    </div>
  );
}
