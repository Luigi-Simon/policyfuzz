import { useEffect, useState } from 'react';
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
  const [agentResult,setAgentResult] = useState<import('./api/transport').AgentSimulationResult>();
  const [agentBusy,setAgentBusy] = useState(false);
  const [agentCompatibilityMode,setAgentCompatibilityMode] = useState(false);
  const [agentError,setAgentError] = useState('');
  const [pendingAgentRequest,setPendingAgentRequest] = useState<AgentSimulationRequest>();
  const currentStep = run ? stageView(run) : 'input';
  const status = agentResult && agentCompatibilityMode && !agentResult.error
    ? 'Agent simulation complete'
    : run ? statusLabel(run) : '';
  useEffect(()=>{if (agentResult) setActive(initialAgentRunId ? 'findings' : 'evidence'); else setActive(currentStep);},[currentStep,run?.run_id,agentResult,initialAgentRunId]);
  useEffect(()=>{setDeleteArmed(false);if (!run) setTitle('');},[run?.run_id]);
  useEffect(()=>{
    if (!initialAgentRunId || !transport.loadAgentSimulation) return;
    const controller = new AbortController();
    setAgentBusy(true);
    transport.loadAgentSimulation(initialAgentRunId, controller.signal)
      .then((result) => setAgentResult(result))
      .catch((reason) => { if (!controller.signal.aborted) setAgentError(reason instanceof Error ? reason.message : 'Stored agent evidence could not be loaded.'); })
      .finally(() => { if (!controller.signal.aborted) setAgentBusy(false); });
    return () => controller.abort();
  },[initialAgentRunId,transport]);
  const display = active === currentStep ? run : snapshots[active];
  const historical = active !== currentStep;
  const available = Object.fromEntries(Object.keys(snapshots).map(step=>[step,true]));
  if (agentResult) { available.evidence = true; available.findings = true; available.comparison = true; }
  const canDelete = run?.allowed_actions?.includes('delete_run') === true;
  const reset = () => {lifecycle.reset();setActive('input');setTitle('');setDeleteArmed(false);setPendingAgentRequest(undefined);setAgentResult(undefined);setAgentError('');setAgentBusy(false);setAgentCompatibilityMode(false);};
  const create = (request:CreateRunRequest) => {setTitle(request.title);void lifecycle.createRun(request);};
  const openAgentEvidence = () => { setActive('evidence'); window.setTimeout(() => document.getElementById('agent-evidence')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0); };
  const queueAgentSimulation = (request:AgentSimulationRequest) => { setPendingAgentRequest(request); setAgentResult(undefined); setAgentError(''); };
  useEffect(() => {
    if (!pendingAgentRequest || !run || agentBusy || agentResult) return;
    const readyStages = new Set(['awaiting_finding_review', 'completed_no_findings', 'completed_no_revision', 'complete']);
    const terminalFailure = new Set(['failed', 'contract_rejected', 'coverage_limit_exceeded', 'revision_rejected']);
    const compatibilityFailure = run.stage === 'failed'
      && (run.error?.code === 'MALFORMED_MODEL_OUTPUT' || run.error?.code === 'PROVIDER_UNAVAILABLE')
      && transport.startCustomAgentSimulation;
    const launch = (compatibility: boolean) => {
      const request = { ...pendingAgentRequest, confirmedRunId: run.run_id };
      setPendingAgentRequest(undefined);
      setActive('evidence');
      setAgentBusy(true);
      setAgentCompatibilityMode(compatibility);
      setAgentError('');
      const starter = compatibility ? transport.startCustomAgentSimulation : transport.startAgentSimulation;
      if (!starter) {
        setAgentBusy(false);
        setAgentError('The local MiroFish compatibility path is unavailable.');
        return;
      }
      // Keep the transport instance as the receiver. HttpTransport methods use
      // `this.request(...)`, so invoking a detached method breaks the fallback
      // with "Cannot read properties of undefined (reading 'request')".
      const invoke = () => starter.call(transport, request);
      void invoke()
        .then((result) => setAgentResult(result))
        .catch((reason) => setAgentError(reason instanceof Error ? reason.message : 'Agent simulation could not be started.'))
        .finally(() => setAgentBusy(false));
    };
    if (compatibilityFailure) {
      launch(true);
      return;
    }
    if (terminalFailure.has(run.stage)) {
      setPendingAgentRequest(undefined);
      setAgentError('MiroFish was not started because the confirmed PolicyFuzz run did not produce a usable scenario suite.');
      return;
    }
    if (!readyStages.has(run.stage) || !transport.startAgentSimulation) return;
    launch(false);
  }, [agentBusy, agentResult, pendingAgentRequest, run, transport]);
  const remove = () => {if (!deleteArmed) setDeleteArmed(true);else void lifecycle.deleteRun();};
  const compatibilityHandled = agentCompatibilityMode && Boolean(agentResult) && run?.stage === 'failed';

  return <div className="app-shell">
    <AppHeader run={run} busy={busy} onReset={run ? reset : undefined} onDelete={canDelete ? remove : undefined} deleteArmed={deleteArmed} />
    <main id="main-content" tabIndex={-1}>
      <div className="page-heading">
        <p className="eyebrow">{transport.dataSourceLabel ?? 'Public API'}{run ? '' : ' · no run loaded'}</p>
        {title ? <p>{title}</p> : null}
        <StepNavigation active={active} available={available} onNavigate={setActive}/>
      </div>
      {run ? <div className="status-strip" role="status"><strong>{status}</strong>{isPollingStage(run.stage) && !agentResult ? <span>Partial results may change</span> : null}</div> : null}
      {agentResult ? <section className="panel" aria-live="polite"><h3>{agentResult.error ? 'AI agent simulation failed' : agentResult.effectiveness?.interaction_verified ? 'AI agent simulation complete' : 'MiroFish capture complete — replies not verified'}</h3><p><strong>{agentResult.status}</strong> · MiroFish run <code>{agentResult.run_id}</code></p>{agentResult.compatibility_mode ? <p className="notice warning">This custom policy used MiroFish’s generic policy parser because its vocabulary is broader than PolicyFuzz’s typed travel-and-expense contract. No PolicyFuzz rule IDs were invented.</p> : null}{agentResult.effectiveness?.score !== undefined ? <p>Effectiveness score: <strong>{agentResult.effectiveness.score}/100</strong></p> : null}<p className={agentResult.error ? 'small' : 'muted small'}>{agentResult.error ?? (agentResult.effectiveness?.interaction_verified ? 'The complete agent conversation and findings are available in the linked workflow steps.' : 'MiroFish returned posts, but no agent-to-agent replies. Review the evidence and rerun after checking the swarm configuration.')}</p><button type="button" onClick={openAgentEvidence}>{agentResult.error ? 'Review partial evidence' : 'Open full agent evidence'}</button></section> : null}
      {agentBusy ? <section className="panel" role="status" aria-live="polite"><h3>{agentCompatibilityMode ? 'Starting custom-policy MiroFish simulation…' : 'Starting AI agent simulation…'}</h3><p>{agentCompatibilityMode ? 'PolicyFuzz is handing this general policy to MiroFish’s generic parser and agent swarm.' : 'MiroFish is building the scenario, preparing agents, and running their interactions. This can take a few minutes.'}</p><div className="loading" /></section> : null}
      {agentError ? <section className="notice danger" role="alert"><p>{agentError}</p></section> : null}
      {deleteArmed && run ? <section className="panel" aria-label="Delete run confirmation"><p>Delete this run and its retained server data? This cannot be undone.</p><button type="button" className="secondary" disabled={busy} onClick={()=>setDeleteArmed(false)}>Cancel deletion</button></section> : null}
      <ErrorPanel error={error ?? (compatibilityHandled ? undefined : run?.error)}/>
      {error && lifecycle.runId ? <button type="button" className="secondary" disabled={busy} onClick={()=>void lifecycle.refresh()}>Refresh run</button> : null}
      {busy && !run ? <div role="status"><p>Loading run…</p><button type="button" className="secondary" onClick={reset}>Cancel loading</button><p className="muted small">Cancelling stops waiting locally; it does not delete a server run.</p></div> : null}
      {historical ? <p className="notice">Retained public snapshot from this session. Actions apply only to the current review.</p> : null}
      {run && currentStep !== 'input' && !snapshots.input ? <p className="muted small">Earlier detail is unavailable in this session. Only retained public snapshots can be reopened.</p> : null}
      {pendingAgentRequest && run && !agentResult ? <section className="notice" role="status"><p><strong>AI agent simulation is queued.</strong> Confirm the Step 1 contract; MiroFish will start automatically after the confirmed scenario suite is ready.</p></section> : null}
      {active === 'input' ? <InputContractView key={run?.run_id ?? 'new'} run={display} busy={busy || historical} onCreate={create} onAgentSimulation={queueAgentSimulation} onConfirm={request=>void lifecycle.confirmContract(request)}/> : null}
      {active === 'evidence' && agentResult ? <AgentEvidenceView result={agentResult} /> : null}
      {active === 'findings' && agentResult ? <AgentEvidenceView result={agentResult} step="findings" /> : null}
      {active === 'comparison' && agentResult ? <AgentEvidenceView result={agentResult} step="comparison" /> : null}
      {active === 'evidence' && display ? <RunEvidenceView run={display}/> : null}
      {active === 'findings' && display ? <FindingsRevisionView key={run?.run_id} run={display} busy={busy || historical} onSelect={request=>void lifecycle.selectFindings(request)} onConfirm={request=>void lifecycle.confirmRevision(request)}/> : null}
      {active === 'comparison' && display ? <ComparisonView run={display}/> : null}
    </main>
    <footer><span>PolicyFuzz · Public run evidence</span><span>Deterministic results describe this frozen suite.</span></footer>
  </div>;
}
