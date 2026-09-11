import { useEffect, useRef, useState, type FormEvent } from 'react';
import { createWorkflow, loadCapabilities, loadSample, WorkflowError, type Capabilities, type CreateWorkflow, type Policy, type WorkflowRequest, type WorkflowResult } from './workflow-api';
import { WorkflowEvidence } from './WorkflowEvidence';
import './v2.css';

export function WorkflowApp({ run = createWorkflow, capabilities = loadCapabilities, sample = loadSample }: {
  run?: CreateWorkflow; capabilities?: () => Promise<Capabilities>; sample?: () => Promise<Policy>;
}) {
  const [fields, setFields] = useState({ title: '', description: '', agent_seed: '', agent_count: '3' });
  const [mode, setMode] = useState<'fixture' | 'live'>('fixture');
  const [fixture, setFixture] = useState<WorkflowRequest['fixture_name']>('completed');
  const [budget, setBudget] = useState('12');
  const [rounds, setRounds] = useState('2');
  const [minutes, setMinutes] = useState('8');
  const [available, setAvailable] = useState<Capabilities | null>(null);
  const [result, setResult] = useState<WorkflowResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadingSample, setLoadingSample] = useState(false);
  const [error, setError] = useState('');
  const current = useRef<AbortController | null>(null);
  useEffect(() => {
    let active = true;
    capabilities().then(value => { if (active) setAvailable(value); }).catch(() => { if (active) setError('Start the v2 service to load its capabilities.'); });
    return () => { active = false; current.current?.abort(); };
  }, [capabilities]);
  const invalidate = () => {
    setResult(null);
    if (/^#(?:metric-|v2-(?:message|persona|source)-)/.test(window.location.hash)) {
      window.history.replaceState(window.history.state, '', window.location.pathname + window.location.search);
    }
  };
  const edit = (key: keyof typeof fields, value: string) => { setFields(previous => ({ ...previous, [key]: value })); invalidate(); };
  async function example() {
    setLoadingSample(true); setError('');
    try { const policy = await sample(); setFields({ ...policy, agent_count: String(policy.agent_count) }); invalidate(); }
    catch { setError('The synthetic example could not be loaded. Check the v2 service.'); }
    finally { setLoadingSample(false); }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (current.current) return;
    const count = Number(fields.agent_count), tests = Number(budget), maxRounds = Number(rounds), timeoutMinutes = Number(minutes);
    if (![fields.title, fields.description, fields.agent_seed].every(value => value.trim()) || !Number.isInteger(count) || count < 1 || count > 100 || !Number.isInteger(tests) || tests < 1 || tests > 12 || !Number.isInteger(maxRounds) || maxRounds < 1 || maxRounds > 20 || !Number.isInteger(timeoutMinutes) || timeoutMinutes < 1 || timeoutMinutes > 10) {
      setError('Complete the four policy fields and use valid whole-number run settings.'); return;
    }
    if (mode === 'live' && !available?.live_available) { setError('Live services are not configured on the server.'); return; }
    const controller = new AbortController(); current.current = controller;
    setBusy(true); setError(''); invalidate();
    try {
      const response = await run({ policy: { ...fields, agent_count: count }, mode, fixture_name: fixture, test_budget: tests, max_rounds: maxRounds, sandbox_timeout_seconds: timeoutMinutes * 60 }, controller.signal);
      if (!controller.signal.aborted) setResult(response);
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof WorkflowError ? cause.message : 'The workflow could not be reached. Check the local services.');
    } finally { if (!controller.signal.aborted) { setBusy(false); current.current = null; } }
  }
  return <div className="v2-app">
    <a className="skip" href="#workflow-main">Skip to policy input</a>
    <header><div className="v2-topbar"><a href="/v2" className="v2-brand"><h1>PolicyFuzz <span className="badge">v2</span></h1></a><span className="badge">{mode === 'live' ? 'Live workflow selected' : 'Fixture workflow'}</span><a href="/v2/fixture">Sandbox demo</a><a href="/">Open v1</a></div></header>
    <main className="v2-content" id="workflow-main">
      <div className="v2-intro"><p className="eyebrow">FOUR AGENTS · ONE WORKFLOW</p><h2>Test the rules.<br/>Hear the people.</h2><p>Metric test evidence and stakeholder conversations feed a cited Judge report.</p></div>
      <div className={`notice ${mode === 'live' ? 'neutral' : 'warning'}`}><p>{mode === 'live' ? 'Live mode sends your policy and personality seed to the configured model provider and runs MiroFish participants. Use synthetic or explicitly non-confidential text. Live runs can take several minutes.' : 'Fixture mode runs real deterministic Metric tests with authored Sandbox dialogue and demonstration Judge advice. The dialogue does not analyse your policy or personality seed.'}</p></div>
      <div className="v2-input-grid"><section className="panel"><div className="row"><h3>Policy input</h3><button className="secondary" disabled={busy || loadingSample} onClick={example}>{loadingSample ? 'Loading example…' : 'Load synthetic example'}</button></div>
        <p className="muted small">Metric executes the documented reimbursement model and supported numeric comparisons, including explicit rest, work-hour and notice thresholds. Unsupported rules and exceptions receive unscored scenario questions; Judge reviews the evidence with those limits.</p>
        <form onSubmit={submit}><fieldset disabled={busy || loadingSample} className="v2-fields">
          <label className="field">Policy title<input required maxLength={200} value={fields.title} onChange={e => edit('title', e.target.value)} placeholder="English policy title"/></label>
          <label className="field">Policy description<textarea required maxLength={50000} rows={8} value={fields.description} onChange={e => edit('description', e.target.value)}/></label>
          <label className="field">Personality seed<textarea required maxLength={2000} rows={3} value={fields.agent_seed} onChange={e => edit('agent_seed', e.target.value)}/></label>
          <label className="field">Stakeholder count<input required type="number" min={1} max={100} step={1} value={fields.agent_count} onChange={e => edit('agent_count', e.target.value)}/><small>Live Sandbox currently configures at most 50; larger requests remain visibly partial.</small></label>
          <label className="field">Execution mode<select value={mode} onChange={e => { setMode(e.target.value as 'fixture' | 'live'); invalidate(); }}><option value="fixture">Fixture workflow · no provider calls</option><option value="live" disabled={!available?.live_available}>Live MiroFish and Judge</option></select><small>{available?.live_detail ?? 'Checking server configuration…'}</small></label>
          <details><summary>Run settings</summary><div className="v2-form-bottom"><label className="field">Metric test budget<input type="number" required min={1} max={12} value={budget} onChange={e => { setBudget(e.target.value); invalidate(); }}/></label><label className="field">Simulation rounds<input type="number" required min={1} max={20} value={rounds} onChange={e => { setRounds(e.target.value); invalidate(); }}/></label></div>
            <label className="field">Sandbox time limit (minutes)<input type="number" required min={1} max={10} value={minutes} onChange={e => { setMinutes(e.target.value); invalidate(); }}/><small>Includes participant setup, simulation and evidence capture. Judge review follows separately.</small></label>
            {mode === 'fixture' && <label className="field">Fixture sample<select value={fixture} onChange={e => { setFixture(e.target.value as WorkflowRequest['fixture_name']); invalidate(); }}><option value="completed">Complete sample</option><option value="partial_translation_unavailable">Translation unavailable sample</option></select></label>}
          </details>
        </fieldset>{error && <p role="alert" className="form-error v2-error">{error}</p>}
          <div className="actions"><button className="primary" type="submit" disabled={busy || loadingSample}>{busy ? 'Running workflow…' : mode === 'live' ? 'Run live workflow' : 'Run fixture workflow'}</button></div>
        </form>
      </section><aside className="panel v2-roles"><h3>From input to evidence</h3><ol>{[
        ['Orchestrator Agent', 'Binds one policy version and validates every handoff.'],
        ['Metric Agent', 'Executes supported rules and prepares unscored scenarios where an executable interpretation is unavailable.'],
        ['Sandbox Agent', 'Uses MiroFish to generate personalities and capture stakeholder replies.'],
        ['Judge Agent', 'Returns cited pros, cons, recommendations and next steps.'],
      ].map(([name, text], index) => <li key={name}><span className="stepnum">{index + 1}</span><div><strong>{name}</strong><p>{text}</p></div></li>)}</ol><p className="small muted">Live evidence stays in MiroFish's local records. This page does not retain results after reload.</p></aside></div>
      <div role="status" aria-live="polite" className={busy ? 'notice neutral' : 'v2-status'}>{busy ? 'The Orchestrator is running Metric, Sandbox and Judge. Keep this page open while the bounded run completes.' : result ? `Workflow ${result.status}. Evidence is available below.` : ''}</div>
      {result && <WorkflowEvidence result={result}/>}
    </main><footer>PolicyFuzz · Evidence for proposed policies</footer>
  </div>;
}
