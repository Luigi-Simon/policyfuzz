import { useState, type FormEvent } from 'react';
import { Check, FileText, ShieldCheck } from 'lucide-react';
import type { ConfirmContractRequest, CreateRunRequest, InvariantSummary, RunView } from '../api/types';
import { HashValue } from '../components/HashValue';
import { OutcomeBadge } from '../components/OutcomeBadge';
import { SourceCitation } from '../components/SourceCitation';

const bundledSamples = [{ id: 'development-policy', label: 'Development reimbursement policy' }] as const;

export interface InputContractViewProps {
  run?: RunView | null;
  busy: boolean;
  onCreate: (request: CreateRunRequest) => void;
  onConfirm: (request: ConfirmContractRequest) => void;
  onAgentSimulation?: (request: { title: string; text: string; seedText: string; populationSize: number; groups: string }) => void;
}

function valueText(value: unknown) {
  return Array.isArray(value) ? value.join(', ') : String(value);
}

function predicateText(predicate: InvariantSummary['when'][number]) {
  return `${predicate.field} ${predicate.operator} ${valueText(predicate.value)}`;
}

function codePointLength(value: string) {
  return Array.from(value).length;
}

export function InputContractView({ run, busy, onCreate, onConfirm, onAgentSimulation }: InputContractViewProps) {
  const [sourceType, setSourceType] = useState<CreateRunRequest['source_type']>('pasted_text');
  const [title, setTitle] = useState('');
  const [text, setText] = useState('');
  const [sampleId, setSampleId] = useState<string>(bundledSamples[0].id);
  const [nonConfidential, setNonConfidential] = useState(false);
  const [message, setMessage] = useState('');
  const [agentEnabled, setAgentEnabled] = useState(false);
  const [seedText, setSeedText] = useState('Employees, managers and finance reviewers discuss expense claims, unclear wording and exceptions.');
  const [populationSize, setPopulationSize] = useState(12);
  const pending = run?.pending_confirmation?.kind === 'contract' ? run.pending_confirmation : null;
  const [ruleAcknowledgements, setRuleAcknowledgements] = useState<Record<string, boolean>>({});
  const [dimensionAcknowledgements, setDimensionAcknowledgements] = useState<Record<string, boolean>>({});
  const [selectedInvariantIds, setSelectedInvariantIds] = useState<Record<string, boolean>>({});

  const invariantIsSelected = (id: string) => selectedInvariantIds[id] ?? true;

  const create = (event: FormEvent) => {
    event.preventDefault();
    setMessage('');
    if (!title.trim()) return setMessage('Enter a policy title.');
    if (!nonConfidential) return setMessage('Confirm that the source is non-confidential.');
    if (sourceType === 'pasted_text' && (codePointLength(text) < 1 || codePointLength(text) > 50_000)) {
      return setMessage('Policy text must contain between 1 and 50,000 characters.');
    }
    const normalizedSampleId = sampleId.trim();
    if (sourceType === 'bundled_sample' && (codePointLength(normalizedSampleId) < 1 || codePointLength(normalizedSampleId) > 200)) {
      return setMessage('Bundled sample ID must contain between 1 and 200 characters.');
    }
    if (agentEnabled && onAgentSimulation && sourceType === 'pasted_text') {
      if (!seedText.trim()) return setMessage('Enter an agent seed before starting the simulation.');
      if (!Number.isInteger(populationSize) || populationSize < 1 || populationSize > 50) return setMessage('Agent count must be a whole number between 1 and 50.');
    }
    const agentRequest = agentEnabled && onAgentSimulation && sourceType === 'pasted_text'
      ? { title: title.trim(), text, seedText: seedText.trim(), populationSize, groups: 'employees,managers,finance reviewers' }
      : null;
    if (agentRequest) onAgentSimulation?.(agentRequest);
    onCreate({
      schema_version: '1.0',
      source_type: sourceType,
      title: title.trim(),
      text: sourceType === 'pasted_text' ? text : null,
      sample_id: sourceType === 'bundled_sample' ? normalizedSampleId : null,
      non_confidential_confirmed: true,
    });
  };

  const confirm = () => {
    if (!pending) return;
    setMessage('');
    const invariants = pending.invariants.filter((item) => invariantIsSelected(item.invariant_id));
    if (invariants.length < 3 || invariants.length > 5) return setMessage('Confirm between 3 and 5 intent invariants.');
    const unacknowledgedRule = pending.rules.find((rule) => !ruleAcknowledgements[rule.rule_id]);
    if (unacknowledgedRule) return setMessage(`Acknowledge rule ${unacknowledgedRule.rule_id}.`);
    const missingDimension = pending.required_dimensions.find((dimension) => !dimensionAcknowledgements[dimension]);
    if (missingDimension) return setMessage(`Confirm required dimension ${missingDimension.replaceAll('_', ' ')}.`);
    onConfirm({
      schema_version: '1.0',
      decision: 'confirm',
      baseline_policy_id: pending.baseline_policy_id,
      baseline_policy_sha256: pending.baseline_policy_sha256,
      invariants,
      required_dimensions: pending.required_dimensions,
    });
  };

  if (!pending) {
    return (
      <div className="content">
        <section className="page-title">
          <div>
            <span className="eyebrow">Step 1</span>
            <h2>Policy input</h2>
            <p>Start with a bundled synthetic sample or paste non-confidential policy text.</p>
          </div>
        </section>
        {run ? (
          <section className="panel terminal">
            <h3>{run.stage.replaceAll('_', ' ')}</h3>
            <p>The contract details are unavailable in this public snapshot.</p>
          </section>
        ) : (
          <form className="input-grid" onSubmit={create}>
            <section className="panel">
              <div className="section-heading"><span className="iconbox"><FileText aria-hidden="true" /></span><div><span className="eyebrow">Source</span><h3>Provide a policy</h3></div></div>
              <fieldset className="segmented">
                <legend>Policy source</legend>
                <label><input type="radio" name="source" disabled={busy} checked={sourceType === 'pasted_text'} onChange={() => setSourceType('pasted_text')} /> Pasted text</label>
                <label><input type="radio" name="source" disabled={busy} checked={sourceType === 'bundled_sample'} onChange={() => setSourceType('bundled_sample')} /> Bundled sample</label>
              </fieldset>
              <label className="field">Policy title<input value={title} disabled={busy} onChange={(event) => setTitle(event.target.value)} /></label>
              {sourceType === 'pasted_text' ? (
                <label className="field">Policy text<textarea aria-label="Policy text" rows={16} value={text} disabled={busy} onChange={(event) => setText(event.target.value)} aria-describedby="policy-length" /><small id="policy-length">{codePointLength(text).toLocaleString()} / 50,000 characters</small></label>
              ) : (
                <label className="field">Bundled policy sample<select value={sampleId} disabled={busy} onChange={(event) => setSampleId(event.target.value)}>{bundledSamples.map((sample) => <option key={sample.id} value={sample.id}>{sample.label}</option>)}</select></label>
              )}
            </section>
            <aside>
              <section className="panel sample-card">
                <ShieldCheck className="iconbox large" aria-hidden="true" />
                <h3>Private by design</h3>
                <div className="disclosure"><p>The source stays in memory for up to 60 minutes. Delete the run sooner from the header. Provider processing is disclosed by the configured service.</p></div>
                <label className="checkbox"><input type="checkbox" checked={nonConfidential} disabled={busy} onChange={(event) => setNonConfidential(event.target.checked)} /> I confirm this policy is non-confidential and may be processed by the configured provider.</label>
                {onAgentSimulation ? <><label className="checkbox"><input type="checkbox" checked={agentEnabled && sourceType === 'pasted_text'} disabled={busy || sourceType !== 'pasted_text'} onChange={(event) => setAgentEnabled(event.target.checked)} /> Enable AI agents for an independent MiroFish simulation</label>{sourceType !== 'pasted_text' ? <p className="small muted">Paste non-confidential policy text to enable independent agent simulation.</p> : null}</> : null}
                {onAgentSimulation && agentEnabled && sourceType === 'pasted_text' ? <div className="inset"><p className="small">After the PolicyFuzz contract review and initial tests, MiroFish separately interprets the original text and generates its own scenarios. Its observations do not change the deterministic verdicts or frozen test suite. MiroFish processes and retains its own copy; deleting the PolicyFuzz run does not delete that separate simulation.</p><label className="field">Agent seed<textarea rows={3} value={seedText} disabled={busy} onChange={(event) => setSeedText(event.target.value)} /></label><label className="field">Agent count<input type="number" min={1} max={50} value={populationSize} disabled={busy} onChange={(event) => setPopulationSize(Number(event.target.value))} /></label></div> : null}
                {message ? <p role="alert" className="form-error">{message}</p> : null}
                <button className="wide" disabled={busy} type="submit">{busy ? 'Starting…' : 'Analyze policy'}</button>
              </section>
            </aside>
          </form>
        )}
      </div>
    );
  }

  return (
    <div className="content">
      <section className="page-title">
        <div><span className="eyebrow">Step 1 · Review</span><h2>Confirm policy contract</h2><p>Confirm the server-held baseline and the typed rules and invariants that will govern the run.</p></div>
      </section>
      <div className="review-grid">
        <div>
          <section className="panel">
            <div className="section-heading"><span className="iconbox"><ShieldCheck aria-hidden="true" /></span><div><span className="eyebrow">Extracted contract</span><h3>{pending.rules.length} rules</h3></div></div>
            <HashValue label="Baseline policy hash" value={pending.baseline_policy_sha256} />
            <HashValue label="Document hash" value={pending.document_sha256} />
          </section>
          <div className="rule-stack">
            {pending.rules.map((rule) => (
              <article className="panel" key={rule.rule_id}>
                <div className="row"><h3>{rule.rule_id} · {rule.description}</h3><OutcomeBadge label={`Revision ${rule.revision}`} tone="info" /></div>
                <div className="logic">
                  <div><span className="eyebrow">When</span>{rule.when.length ? rule.when.map((predicate, index) => <code key={index}>{predicate.field} {predicate.operator} {valueText(predicate.value)}</code>) : <code>Always</code>}</div>
                  <div><span className="eyebrow">Effects</span>{rule.effects.map((effect, index) => <code className="teal" key={index}>{effect.dimension.replaceAll('_', ' ')} = {effect.value}</code>)}</div>
                </div>
                {(rule.overrides ?? []).length ? <div className="inset"><span className="eyebrow">Dimension overrides</span>{(rule.overrides ?? []).map((override, index) => <p key={index}>{override.dimension.replaceAll('_', ' ')} overrides {override.target_rule_id}</p>)}</div> : null}
                {rule.confidence_percent === null ? <p className="muted">Extraction confidence: unavailable</p> : <p className="muted">Extraction confidence: {rule.confidence_percent}% · display only</p>}
                {rule.citations.map((citation) => <SourceCitation key={citation.citation_id} citation={citation.span} />)}
                <label className="checkbox"><input type="checkbox" checked={ruleAcknowledgements[rule.rule_id] ?? false} disabled={busy} onChange={(event) => setRuleAcknowledgements((current) => ({ ...current, [rule.rule_id]: event.target.checked }))} /> Acknowledge rule {rule.rule_id}</label>
              </article>
            ))}
          </div>
        </div>
        <aside>
          <section className="panel">
            <h3>Intent invariants</h3>
            <p className="muted">Select 3–5 typed invariants. Their conditions and assertions are submitted unchanged.</p>
            {pending.invariants.map((invariant) => (
              <div className="intent" key={invariant.invariant_id}>
                <label className="checkbox"><input type="checkbox" checked={invariantIsSelected(invariant.invariant_id)} disabled={busy} onChange={(event) => setSelectedInvariantIds((current) => ({ ...current, [invariant.invariant_id]: event.target.checked }))} /> Include {invariant.invariant_id}</label>
                <p>{invariant.description}</p>
                <OutcomeBadge label={invariant.severity} tone={invariant.severity === 'critical' || invariant.severity === 'high' ? 'danger' : 'warning'} />
                <div>{invariant.when.map((predicate, index) => <code key={index}>{predicateText(predicate)}</code>)}</div>
                <code>{invariant.assertion.target_kind} · {invariant.assertion.dimension} {invariant.assertion.operator} {valueText(invariant.assertion.expected_value)}</code>
              </div>
            ))}
          </section>
          <section className="panel">
            <h3>Required dimensions</h3>
            {pending.required_dimensions.map((dimension) => <label className="checkbox" key={dimension}><input type="checkbox" checked={dimensionAcknowledgements[dimension] ?? false} disabled={busy} onChange={(event) => setDimensionAcknowledgements((current) => ({ ...current, [dimension]: event.target.checked }))} /> Confirm required dimension {dimension.replaceAll('_', ' ')}</label>)}
          </section>
          {(run?.unsupported_clauses ?? []).length ? <section className="panel"><h3>Unsupported clauses</h3>{(run?.unsupported_clauses ?? []).map((clause) => <article className="intent" key={clause.clause_id}><div className="row"><code>{clause.clause_id}</code><OutcomeBadge label={clause.disposition.replaceAll('_', ' ')} tone="warning" /></div><p>{clause.reason_code.replaceAll('_', ' ')}</p><p>Affected: {clause.affected_dimensions.map((item) => item.replaceAll('_', ' ')).join(', ')}</p><SourceCitation citation={clause.span} /></article>)}</section> : null}
        </aside>
      </div>
      <section className="panel approval">
        {message ? <p role="alert" className="form-error">{message}</p> : null}
        <div className="actions">
          <button type="button" className="danger" disabled={busy || !(run?.allowed_actions ?? []).includes('reject_contract')} onClick={() => onConfirm({ schema_version: '1.0', decision: 'reject', baseline_policy_id: null, baseline_policy_sha256: null, invariants: [], required_dimensions: [] })}>Reject policy contract</button>
          <button type="button" disabled={busy || !(run?.allowed_actions ?? []).includes('confirm_contract')} onClick={confirm}><Check aria-hidden="true" size={17} /> Confirm policy contract</button>
        </div>
      </section>
    </div>
  );
}
