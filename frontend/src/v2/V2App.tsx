import { useEffect,useRef,useState,type FormEvent } from 'react';
import { ArrowRight,FlaskConical,Network } from 'lucide-react';
import { createFixtureRun,FixtureError,type CreateRun,type PublicResult,type RunRequest } from './api';
import { MetricEvidence,MetricReviewPanel } from './MetricEvidence';
import { loadMetricSample,prepareMetricReview,runMetricTests,MetricError,type LoadMetricSample,type MetricReview,type MetricRunResult,type PrepareMetric,type RunMetric,type RunPolicyInput } from './metric-api';
import { SandboxEvidence } from './SandboxEvidence';
import './v2.css';
const sample={ title: 'Synthetic late-night transit pilot',description: 'The city will extend late-night transit service for six months and review ridership, accessibility, worker safety, and operating cost each month.',agent_seed: 'Include practical, safety-focused, and accessibility-focused voices.',agent_count: '3' };
type Busy='fixture'|'sample'|'review'|'run'|null;
export function V2App({ createRun=createFixtureRun,loadMetricSample: loadSample=loadMetricSample,prepareMetric=prepareMetricReview,runMetric=runMetricTests }: {
  createRun?: CreateRun;
  loadMetricSample?: LoadMetricSample;
  prepareMetric?: PrepareMetric;
  runMetric?: RunMetric;
}) {
  const [fields,setFields]=useState({ title: '',description: '',agent_seed: '',agent_count: '3' });
  const [fixture,setFixture]=useState<RunRequest['fixture_name']>('completed');
  const [result,setResult]=useState<PublicResult|null>(null);
  const [review,setReview]=useState<MetricReview|null>(null);
  const [metricResult,setMetricResult]=useState<MetricRunResult|null>(null);
  const [busyAction,setBusyAction]=useState<Busy>(null);
  const [error,setError]=useState('');
  const current=useRef<AbortController|null>(null);
  const busy=busyAction!==null;
  useEffect(() => () => { current.current?.abort(); },[]);
  const clearMetric=() => { setReview(null); setMetricResult(null); };
  const clearSandbox=() => setResult(null);
  const clearEvidence=() => { clearMetric(); clearSandbox(); };
  const edit=(key: keyof typeof fields,value: string) => {
    clearEvidence();
    setError('');
    setFields(previous => ({ ...previous,[key]: value }));
  };
  function policy(): RunPolicyInput|null {
    const agent_count=Number(fields.agent_count); if(![fields.title,fields.description,fields.agent_seed].every(v => v.trim())||!Number.isInteger(agent_count)||agent_count<1||agent_count>100) {
      setError('Complete all four fields and use a whole stakeholder count from 1 to 100.');
      return null;
    } return { ...fields,agent_count };
  }
  function begin(action: Exclude<Busy,null>) {
    if(current.current)
      return null; const controller=new AbortController(); current.current=controller; setBusyAction(action); setError(''); return controller;
  }
  function finish(controller: AbortController) {
    if(!controller.signal.aborted&&current.current===controller) {
      current.current=null;
      setBusyAction(null);
    }
  }
  const failure=(cause: unknown,fallback: string) => setError((cause instanceof MetricError&&cause.displaySafe)||cause instanceof FixtureError? cause.message:fallback);
  async function submitFixture(event: FormEvent) {
    event.preventDefault(); const input=policy(); const controller=input&&begin('fixture'); if(!controller)
      return; clearEvidence(); try {
        const response=await createRun({ policy: input!,fixture_name: fixture },controller.signal);
        if(!controller.signal.aborted&&current.current===controller)
          setResult(response);
      }
    catch(cause) {
      if(!controller.signal.aborted&&current.current===controller)
        failure(cause,'Could not reach the v2 service. Check that it is running, then retry.');
    }
    finally {
      finish(controller);
    }
  }
  async function transportExample() {
    const controller=begin('sample'); if(!controller)
      return; clearEvidence(); try {
        const input=await loadSample(controller.signal);
        if(!controller.signal.aborted&&current.current===controller) {
          setFields({ ...input,agent_count: String(input.agent_count) });
        }
      }
    catch(cause) {
      if(!controller.signal.aborted&&current.current===controller)
        failure(cause,'The transport claims example could not be loaded. Please retry.');
    }
    finally {
      finish(controller);
    }
  }
  async function reviewRules() {
    const input=policy(); const controller=input&&begin('review'); if(!controller)
      return; clearEvidence(); try {
        const response=await prepareMetric(input!,controller.signal);
        if(!controller.signal.aborted&&current.current===controller)
          setReview(response);
      }
    catch(cause) {
      if(!controller.signal.aborted&&current.current===controller)
        failure(cause,'The Metric service could not review this policy. Please retry.');
    }
    finally {
      finish(controller);
    }
  }
  async function runRules() {
    const input=policy(); if(!input||!review||review.status!=='ready')
      return; const controller=begin('run'); if(!controller)
      return; clearSandbox(); setMetricResult(null); try {
        const response=await runMetric(input,review,controller.signal);
        if(!controller.signal.aborted&&current.current===controller)
          setMetricResult(response);
      }
    catch(cause) {
      if(!controller.signal.aborted&&current.current===controller)
        failure(cause,'The Metric service could not complete. Please retry.');
    }
    finally {
      finish(controller);
    }
  }
  return <div className="v2-app">
    <a className="skip" href="#v2-main">Skip to policy input</a>
<header>
<div className="v2-topbar">
<a href="/v2" className="v2-brand">
<span className="logo" aria-hidden="true">P<span>f</span>
</span>
<h1>PolicyFuzz <span className="badge">v2</span>
</h1>
</a>
<span className="badge warning">
<FlaskConical size={14} aria-hidden="true" />Synthetic demo</span>
<a className="v2-legacy" href="/">Open v1</a>
</div>
</header>
    <main id="v2-main" className="v2-content">
<div className="v2-intro">
<p className="eyebrow">POLICY STRESS TESTING · METRIC + SANDBOX DEMO</p>
<h2>Start with a policy.<br />Inspect the evidence.</h2>
<p>Review deterministic transport-claims rules, then inspect separate Sandbox fixture evidence.</p>
</div>
      <div className="notice neutral v2-disclosure">
<FlaskConical size={22} aria-hidden="true" />
<div>
<strong>This is an integration demo.</strong>
<p>Metric uses deterministic rule-derived templates for one supported synthetic Singapore transport claims domain. Sandbox evidence remains an authored fixture; Judge development is in progress.</p>
</div>
</div>
      <div className="v2-input-grid">
<section className="panel">
<div className="row v2-input-actions">
<h3>Policy input</h3>
<div>
<button type="button" className="secondary" disabled={busy} onClick={() => { setFields(sample); clearEvidence(); setError(''); }}>Load synthetic example</button>
<button type="button" className="secondary" disabled={busy} onClick={transportExample}>{busyAction==='sample'? 'Loading transport claims example…':'Load transport claims example'}</button>
</div>
</div>
<p className="muted small">Use synthetic or explicitly non-confidential text. This fixture API does not save submissions.</p>
        <form onSubmit={submitFixture}>
<fieldset disabled={busy} className="v2-fields">
<label className="field" htmlFor="v2-title">Policy title<input id="v2-title" aria-label="Policy title" required maxLength={200} value={fields.title} onChange={e => edit('title',e.target.value)} placeholder="Give your proposed policy a title" />
<small className="muted">Use an English title.</small>
</label>
<div className="field">
<label id="v2-description-label" htmlFor="v2-description">Policy description</label>
<textarea id="v2-description" aria-labelledby="v2-description-label" aria-describedby="v2-description-help" required maxLength={50000} rows={5} value={fields.description} onChange={e => edit('description',e.target.value)} placeholder="Describe the proposed rules and who they affect." />
<small id="v2-description-help" className="muted">Use synthetic or explicitly non-confidential policy text.</small>
</div>
<div className="field">
<label id="v2-seed-label" htmlFor="v2-seed">Personality seed</label>
<textarea id="v2-seed" aria-labelledby="v2-seed-label" aria-describedby="v2-seed-help" required maxLength={2000} rows={2} value={fields.agent_seed} onChange={e => edit('agent_seed',e.target.value)} placeholder="Describe the stakeholder perspectives to include." />
<small id="v2-seed-help" className="muted">Personality instructions for Sandbox participants.</small>
</div>
<div className="v2-form-bottom">
<label className="field" htmlFor="v2-count">Stakeholder count<input id="v2-count" aria-label="Stakeholder count" type="number" required min={1} max={100} step={1} value={fields.agent_count} onChange={e => edit('agent_count',e.target.value)} />
<small className="muted">1–100 participants inside the Sandbox.</small>
</label>
<label className="field" htmlFor="v2-fixture">Fixture sample<select id="v2-fixture" aria-label="Fixture sample" value={fixture} onChange={e => { setFixture(e.target.value as RunRequest['fixture_name']); clearEvidence(); }}>
<option value="completed">Complete sample</option>
<option value="partial_translation_unavailable">Translation unavailable sample</option>
</select>
<small className="muted">Demo control for the evidence screen.</small>
</label>
</div>
</fieldset>{error&&<p role="alert" className="form-error v2-error">{error}</p>}<div className="actions">
<button className="primary" disabled={busy} type="button" onClick={reviewRules}>{busyAction==='review'? 'Reviewing rules…':'Review policy rules'}</button>
<button className="secondary" disabled={busy} type="submit">{busyAction==='fixture'? 'Running fixture…':'Run fixture'}<ArrowRight size={17} aria-hidden="true" />
</button>
</div>
</form>
      </section>
<aside className="panel v2-roles">
<h3>
<Network size={20} aria-hidden="true" />Four roles. One workflow.</h3>
<p className="small muted">The v2 architecture, built in stages.</p>
<ol>{[['Metric Agent','Interprets one supported domain into deterministic rule-derived templates.','Available'],['Orchestrator Agent','Binds your inputs and coordinates the run.','Available'],['Sandbox Agent','Returns the authored stakeholder sample.','Fixture adapter'],['Judge Agent','Will weigh evidence and recommend next steps.','In development']].map(([name,description,label],index) => <li key={name}>
<span className="stepnum">{index+1}</span>
<div>
<strong>{name}</strong>
<p>{description}</p>
<span className="badge">{label}</span>
</div>
</li>)}</ol>
<p className="v2-role-note">The stakeholder count controls participants inside the Sandbox, not the number of top-level roles or Metric test cases.</p>
</aside>
</div>
      <div role="status" aria-live="polite" className={busy? 'notice neutral':'v2-status'}>{busyAction==='fixture'? 'The Orchestrator is requesting and validating fixture evidence…':busyAction==='sample'? 'Loading the transport claims example…':busyAction==='review'? 'Metric is interpreting supported policy rules…':busyAction==='run'? 'Metric is running deterministic rule-derived templates…':result? `Fixture run ${result.status}. Sandbox evidence is available below.`:''}</div>{review&&<MetricReviewPanel review={review} busy={busy} onRun={runRules} />} {metricResult&&<MetricEvidence result={metricResult} />} {result&&<SandboxEvidence result={result} />}</main>
<footer>
<span>PolicyFuzz v2 · Proposed policies, inspected before release.</span>
<span>Milestone 2 · Synthetic evidence only</span>
</footer>
  </div>;
}
