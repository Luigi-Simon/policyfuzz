import { useEffect, useRef, useState } from 'react';
import type { PolicyFuzzTransport } from './api/transport';
import type { CreateRunRequest, RunView } from './api/types';
import type { AgentSimulationRequest } from './api/transport';
import { AppHeader } from './components/AppHeader';
import { ErrorPanel } from './components/ErrorPanel';
import { StepNavigation } from './components/StepNavigation';
import { InputContractView } from './views/InputContractView';
import { RunEvidenceView } from './views/RunEvidenceView';
import { FindingsRevisionView } from './views/FindingsRevisionView';
import { ComparisonView } from './views/ComparisonView';
import { AgentEvidenceView } from './views/AgentEvidenceView';
import { isPollingStage, stageView, type ViewStep } from './state/stageView';
import { usePolicyFuzzRun } from './state/usePolicyFuzzRun';
import { useAgentSimulation } from './state/useAgentSimulation';

function statusLabel(run:RunView):string {
  if (isPollingStage(run.stage)) return `Running · ${run.stage.replaceAll('_',' ')}`;
  const labels:Partial<Record<RunView['stage'],string>> = {
    awaiting_contract:'Awaiting owner contract review', awaiting_finding_review:'Awaiting finding review',
    awaiting_revision_confirmation:'Awaiting revision confirmation', complete:'Run complete',
    completed_no_findings:'Completed — no reviewable findings', completed_no_revision:'Completed — no revision applied',
    contract_rejected:'Contract rejected — run ended', revision_rejected:'Revision rejected — baseline unchanged',
    coverage_limit_exceeded:'Coverage limit reached', failed:'Run failed',
  };
  return labels[run.stage] ?? run.stage.replaceAll('_',' ');
}

export default function App({transport,initialRunId,initialAgentRunId}:{transport:PolicyFuzzTransport;initialRunId?:string;initialAgentRunId?:string}) {
  const lifecycle = usePolicyFuzzRun(transport,initialRunId);
  const {run,busy,error,snapshots} = lifecycle;
  const [active,setActive] = useState<ViewStep>('input');
  const [deleteArmed,setDeleteArmed] = useState(false);
  const [title,setTitle] = useState('');
  const [inputVersion,setInputVersion] = useState(0);
  const agent = useAgentSimulation(transport, initialAgentRunId);
  const { result: agentResult, busy: agentBusy, error: agentError } = agent;
  const exploratoryOnly = !run && Boolean(agentBusy || agentResult || agentError || agent.runId);
  const [pendingAgentRequest,setPendingAgentRequest] = useState<AgentSimulationRequest>();
  const nextAgentRequest = useRef<AgentSimulationRequest | undefined>(undefined);
  const currentStep = run ? stageView(run) : 'input';
  const status = run ? statusLabel(run) : '';
  useEffect(() => { setActive(currentStep); }, [currentStep, run?.run_id]);
  useEffect(() => { if (agentResult && !run) setActive('evidence'); }, [agentResult, run]);
  useEffect(() => { setDeleteArmed(false); if (!run) setTitle(''); }, [run?.run_id]);
  useEffect(() => {
    const url = new URL(window.location.href);
    if (lifecycle.runId) url.searchParams.set('run_id', lifecycle.runId);
    else url.searchParams.delete('run_id');
    if (agent.runId) url.searchParams.set('mirofish_run', agent.runId);
    else url.searchParams.delete('mirofish_run');
    window.history.replaceState(null, '', url);
  }, [lifecycle.runId, agent.runId]);
  const display = active === currentStep ? run : snapshots[active];
  const historical = active !== currentStep;
  const available = Object.fromEntries(Object.keys(snapshots).map(step=>[step,true]));
  if (agentResult) { available.evidence = true; available.findings = true; }
  const canDelete = run?.allowed_actions?.includes('delete_run') === true;
  const reset = () => {
    nextAgentRequest.current = undefined; agent.reset(); lifecycle.reset(); setActive('input'); setTitle(''); setDeleteArmed(false); setPendingAgentRequest(undefined);
    setInputVersion(version => version + 1);
  };
  const create = (request: CreateRunRequest) => {
    agent.reset();
    setPendingAgentRequest(nextAgentRequest.current);
    nextAgentRequest.current = undefined;
    setTitle(request.title);
    void lifecycle.createRun(request);
  };
  const openAgentEvidence = () => {
    setActive('evidence');
    window.setTimeout(() => document.getElementById('agent-evidence')?.scrollIntoView({ block: 'start' }), 0);
  };
  const queueAgentSimulation = (request: AgentSimulationRequest) => { nextAgentRequest.current = request; };
  const startExploratory = (request: AgentSimulationRequest) => {
    nextAgentRequest.current = undefined;
    setPendingAgentRequest(undefined);
    lifecycle.reset();
    setTitle(request.title);
    setActive('input');
    void agent.launch(request, true);
  };
  const startIndependent = () => {
    if (!pendingAgentRequest || !run) return;
    const request = { ...pendingAgentRequest, confirmedRunId: run.run_id };
    setPendingAgentRequest(undefined);
    void agent.launch(request, true);
  };
  const cancelAgentWaiting = () => { setPendingAgentRequest(undefined); agent.reset(); };
  const canExplore = Boolean(pendingAgentRequest && run?.stage === 'failed'
    && (run.error?.code === 'MALFORMED_MODEL_OUTPUT' || run.error?.code === 'PROVIDER_UNAVAILABLE')
    && transport.supportsAgentSimulation && transport.startCustomAgentSimulation);
  useEffect(() => {
    if (!pendingAgentRequest || !run || agentBusy || agentResult) return;
    const readyStages = new Set(['awaiting_finding_review', 'completed_no_findings', 'completed_no_revision', 'complete']);
    if (!readyStages.has(run.stage) || !transport.supportsAgentSimulation || !transport.startAgentSimulation) return;
    const request = { ...pendingAgentRequest, confirmedRunId: run.run_id };
    setPendingAgentRequest(undefined);
    void agent.launch(request);
  }, [agent.launch, agentBusy, agentResult, pendingAgentRequest, run, transport]);
  const remove = async () => {
    if (!deleteArmed) { setDeleteArmed(true); return; }
    await lifecycle.deleteRun(() => { agent.reset(); setPendingAgentRequest(undefined); setActive('input'); });
  };

  return <div className="app-shell">
    <AppHeader run={run} busy={busy} onReset={run || agentBusy || agentResult || agentError || lifecycle.runId ? reset : undefined} onDelete={canDelete ? () => void remove() : undefined} deleteArmed={deleteArmed} />
    <main id="main-content" tabIndex={-1}>
      <div className="page-heading">
        <p className="eyebrow">{exploratoryOnly ? 'Independent exploratory simulation' : transport.dataSourceLabel ?? 'Public API'}{run || exploratoryOnly ? '' : ' · no run loaded'}</p>
        {title ? <p>{title}</p> : null}
        <StepNavigation active={active} available={available} onNavigate={setActive} exploratory={exploratoryOnly}/>
      </div>
      {run ? <div className="status-strip" role="status"><strong>{status}</strong>{isPollingStage(run.stage) && !agentResult ? <span>Partial results may change</span> : null}</div> : null}
      {agentResult ? <section className="panel" aria-live="polite">
        <h3>{agentResult.error ? 'Independent agent simulation failed' : 'Independent agent evidence available'}</h3>
        <p><strong>{agentResult.status}</strong> · MiroFish run <code>{agentResult.run_id}</code></p>
        <p className="notice warning">Exploratory observations from a separate interpretation of the original policy. This simulation does not reuse the frozen PolicyFuzz suite or establish that a revision works.</p>
        {agentResult.error ? <p>{agentResult.error}</p> : null}
        <button type="button" onClick={openAgentEvidence}>Open full agent evidence</button>
      </section> : null}
      {agentBusy ? <section className="panel" role="status" aria-live="polite">
        <h3>Waiting for independent agent simulation…</h3><p>MiroFish is interpreting the source and collecting exploratory observations. This can take a few minutes.</p>
        <div className="loading" /><button type="button" className="secondary" onClick={cancelAgentWaiting}>Cancel simulation waiting</button>
        <p className="muted small">Cancelling stops waiting locally; the separate server simulation may continue.</p>
      </section> : null}
      {agentError ? <section className="notice danger" role="alert"><p>{agentError}</p></section> : null}
      {canExplore ? <section className="panel">
        <h3>Continue with exploratory observations?</h3>
        <p>The deterministic PolicyFuzz run failed. You can separately submit the original non-confidential text to MiroFish. It will generate its own scenarios without a confirmed PolicyFuzz contract; its results cannot verify a policy revision.</p>
        <button type="button" disabled={agentBusy} onClick={startIndependent}>Start independent exploratory simulation</button>
        <button type="button" className="secondary" onClick={cancelAgentWaiting}>Dismiss simulation</button>
      </section> : null}
      {deleteArmed && run ? <section className="panel" aria-label="Delete run confirmation"><p>Delete this run and its retained server data? This cannot be undone.</p><button type="button" className="secondary" disabled={busy} onClick={()=>setDeleteArmed(false)}>Cancel deletion</button></section> : null}
      <ErrorPanel error={error ?? run?.error}/>
      {error && lifecycle.runId ? <button type="button" className="secondary" disabled={busy} onClick={()=>void lifecycle.refresh()}>Refresh run</button> : null}
      {busy && !run ? <div role="status"><p>Loading run…</p><button type="button" className="secondary" onClick={reset}>Cancel loading</button><p className="muted small">Cancelling stops waiting locally; it does not delete a server run.</p></div> : null}
      {historical ? <p className="notice">Retained public snapshot from this session. Actions apply only to the current review.</p> : null}
      {run && currentStep !== 'input' && !snapshots.input ? <p className="muted small">Earlier detail is unavailable in this session. Only retained public snapshots can be reopened.</p> : null}
      {pendingAgentRequest && run && !agentResult && (isPollingStage(run.stage) || run.stage === 'awaiting_contract') ? <section className="notice" role="status"><p><strong>Independent agent simulation is queued.</strong> After contract review and initial tests, MiroFish separately interprets the original text and generates its own scenarios. Its observations do not change the frozen suite or deterministic verdicts.</p></section> : null}
      {active === 'input' ? <InputContractView key={`${run?.run_id ?? 'new'}-${inputVersion}`} run={display} busy={busy || agentBusy || historical} onCreate={create} onAgentSimulation={transport.supportsAgentSimulation && transport.startAgentSimulation ? queueAgentSimulation : undefined} onExplore={transport.supportsAgentSimulation && transport.startCustomAgentSimulation ? startExploratory : undefined} onConfirm={request=>void lifecycle.confirmContract(request)}/> : null}
      {active === 'evidence' && agentResult ? <AgentEvidenceView result={agentResult} /> : null}
      {active === 'findings' && agentResult ? <AgentEvidenceView result={agentResult} step="findings" /> : null}
      {active === 'evidence' && display ? <RunEvidenceView run={display}/> : null}
      {active === 'findings' && display ? <FindingsRevisionView key={run?.run_id} run={display} busy={busy || historical} onSelect={request=>void lifecycle.selectFindings(request)} onConfirm={request=>void lifecycle.confirmRevision(request)}/> : null}
      {active === 'comparison' && display ? <ComparisonView run={display}/> : null}
    </main>
    <footer><span>PolicyFuzz · Public run evidence</span><span>{exploratoryOnly ? 'Exploratory observations require independent review.' : 'Deterministic results describe this frozen suite.'}</span></footer>
  </div>;
}
