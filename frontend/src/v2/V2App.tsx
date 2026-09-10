import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowRight, FlaskConical, Network } from 'lucide-react';
import { createFixtureRun, FixtureError, type CreateRun, type PublicResult, type RunRequest } from './api';
import { SandboxEvidence } from './SandboxEvidence';
import './v2.css';

const sample = {
  title: 'Synthetic late-night transit pilot',
  description: 'The city will extend late-night transit service for six months and review ridership, accessibility, worker safety, and operating cost each month.',
  agent_seed: 'Include practical, safety-focused, and accessibility-focused voices.',
  agent_count: '3',
};

export function V2App({ createRun = createFixtureRun }: { createRun?: CreateRun }) {
  const [fields, setFields] = useState({ title: '', description: '', agent_seed: '', agent_count: '3' });
  const [fixture, setFixture] = useState<RunRequest['fixture_name']>('completed');
  const [result, setResult] = useState<PublicResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const current = useRef<AbortController | null>(null);
  useEffect(() => () => { current.current?.abort(); }, []);
  const edit = (key: keyof typeof fields, value: string) => setFields(previous => ({ ...previous, [key]: value }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (current.current) return;
    const count = Number(fields.agent_count);
    if (![fields.title, fields.description, fields.agent_seed].every(value => value.trim()) || !Number.isInteger(count) || count < 1 || count > 100) {
      setError('Complete all four fields and use a whole stakeholder count from 1 to 100.');
      return;
    }
    const controller = new AbortController();
    current.current = controller;
    setBusy(true); setError(''); setResult(null);
    try {
      const response = await createRun({ policy: { ...fields, agent_count: count }, fixture_name: fixture }, controller.signal);
      if (!controller.signal.aborted && current.current === controller) setResult(response);
    } catch (cause) {
      if (!controller.signal.aborted && current.current === controller) {
        setError(cause instanceof FixtureError ? cause.message : 'Could not reach the v2 service. Check that it is running, then retry.');
      }
    } finally {
      if (!controller.signal.aborted && current.current === controller) { setBusy(false); current.current = null; }
    }
  }

  return <div className="v2-app">
    <a className="skip" href="#v2-main">Skip to policy input</a>
    <header><div className="v2-topbar"><a href="/v2" className="v2-brand"><span className="logo" aria-hidden="true">P<span>f</span></span><h1>PolicyFuzz <span className="badge">v2</span></h1></a>
      <span className="badge warning"><FlaskConical size={14} aria-hidden="true"/>Synthetic fixture</span><a className="v2-legacy" href="/">Open v1</a></div></header>
    <main id="v2-main" className="v2-content">
      <div className="v2-intro"><p className="eyebrow">POLICY STRESS TESTING · FIRST MILESTONE</p><h2>Start with a policy.<br/>Inspect the evidence.</h2><p>Try the new input and Sandbox handoff with an English fixture.</p></div>
      <div className="notice neutral v2-disclosure"><FlaskConical size={22} aria-hidden="true"/><div><strong>This is an integration demo.</strong><p>Authored dialogue does not analyse your policy or personality seed. No live MiroFish simulation, Metric tests or Judge evaluation runs yet.</p></div></div>
      <div className="v2-input-grid">
        <section className="panel"><div className="row"><h3>Policy input</h3><button type="button" className="secondary" disabled={busy} onClick={() => { setFields(sample); setError(''); setResult(null); }}>Load synthetic example</button></div>
          <p className="muted small">Use synthetic or explicitly non-confidential text. This fixture API does not save submissions.</p>
          <form onSubmit={submit}>
            <fieldset disabled={busy} className="v2-fields">
              <label className="field" htmlFor="v2-title">Policy title<input id="v2-title" aria-label="Policy title" required maxLength={200} value={fields.title} onChange={event => edit('title', event.target.value)} placeholder="Give your proposed policy a title"/><small className="muted">Use an English title.</small></label>
              <label className="field" htmlFor="v2-description">Policy description<textarea id="v2-description" required maxLength={50000} rows={5} value={fields.description} onChange={event => edit('description', event.target.value)} placeholder="Describe the proposed rules and who they affect."/></label>
              <label className="field" htmlFor="v2-seed">Personality seed<textarea id="v2-seed" aria-label="Personality seed" required maxLength={2000} rows={2} value={fields.agent_seed} onChange={event => edit('agent_seed', event.target.value)} placeholder="Describe the stakeholder perspectives to include."/><small className="muted">Personality instructions for Sandbox participants.</small></label>
              <div className="v2-form-bottom"><label className="field" htmlFor="v2-count">Stakeholder count<input id="v2-count" aria-label="Stakeholder count" type="number" required min={1} max={100} step={1} value={fields.agent_count} onChange={event => edit('agent_count', event.target.value)}/><small className="muted">1–100 participants inside the Sandbox.</small></label>
                <label className="field" htmlFor="v2-fixture">Fixture sample<select id="v2-fixture" aria-label="Fixture sample" value={fixture} onChange={event => setFixture(event.target.value as RunRequest['fixture_name'])}><option value="completed">Complete sample</option><option value="partial_translation_unavailable">Translation unavailable sample</option></select><small className="muted">Demo control for the evidence screen.</small></label></div>
            </fieldset>
            {error && <p role="alert" className="form-error v2-error">{error}</p>}
            <div className="actions"><button className="primary" disabled={busy} type="submit">{busy ? 'Running fixture…' : 'Run fixture'}<ArrowRight size={17} aria-hidden="true"/></button></div>
          </form>
        </section>
        <aside className="panel v2-roles"><h3><Network size={20} aria-hidden="true"/>Four agents. One workflow.</h3><p className="small muted">The v2 architecture, built in stages.</p>
          <ol>{[
            ['Orchestrator Agent', 'Binds your inputs and coordinates the run.', 'Available'],
            ['Metric Agent', 'Will generate ordinary and extreme edge cases.', 'Next milestone'],
            ['Sandbox Agent', 'Returns the authored stakeholder sample.', 'Fixture adapter'],
            ['Judge Agent', 'Will weigh evidence and recommend next steps.', 'Next milestone'],
          ].map(([name, description, label], index) => <li key={name}><span className="stepnum">{index + 1}</span><div><strong>{name}</strong><p>{description}</p><span className="badge">{label}</span></div></li>)}</ol>
          <p className="v2-role-note">The stakeholder count controls participants inside the Sandbox, not the number of top-level agents.</p>
        </aside>
      </div>
      <div role="status" aria-live="polite" className={busy ? 'notice neutral' : 'v2-status'}>{busy ? 'The Orchestrator is requesting and validating fixture evidence…' : result ? `Fixture run ${result.status}. Evidence is available below.` : ''}</div>
      {result && <SandboxEvidence result={result}/>}
    </main>
    <footer><span>PolicyFuzz v2 · Proposed policies, inspected before release.</span><span>Milestone 1 · Synthetic evidence only</span></footer>
  </div>;
}
