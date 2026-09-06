import { useEffect, useState } from 'react';
import type { PolicyFuzzTransport } from './api/transport';
import type { CreateRunRequest, RunView } from './api/types';
import { AppHeader } from './components/AppHeader';
import { ErrorPanel } from './components/ErrorPanel';
import { StepNavigation } from './components/StepNavigation';
import { InputContractView } from './views/InputContractView';
import { RunEvidenceView } from './views/RunEvidenceView';
import { FindingsRevisionView } from './views/FindingsRevisionView';
import { ComparisonView } from './views/ComparisonView';
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

export default function App({transport,initialRunId}:{transport:PolicyFuzzTransport;initialRunId?:string}) {
  const lifecycle = usePolicyFuzzRun(transport,initialRunId);
  const {run,busy,error,snapshots} = lifecycle;
  const [active,setActive] = useState<ViewStep>('input');
  const [deleteArmed,setDeleteArmed] = useState(false);
  const [title,setTitle] = useState('');
  const currentStep = run ? stageView(run) : 'input';
  useEffect(()=>{setActive(currentStep);},[currentStep,run?.run_id]);
  useEffect(()=>{setDeleteArmed(false);if (!run) setTitle('');},[run?.run_id]);
  const display = active === currentStep ? run : snapshots[active];
  const historical = active !== currentStep;
  const available = Object.fromEntries(Object.keys(snapshots).map(step=>[step,true]));
  const canDelete = run?.allowed_actions?.includes('delete_run') === true;
  const reset = () => {lifecycle.reset();setActive('input');setTitle('');setDeleteArmed(false);};
  const create = (request:CreateRunRequest) => {setTitle(request.title);void lifecycle.createRun(request);};
  const remove = () => {if (!deleteArmed) setDeleteArmed(true);else void lifecycle.deleteRun();};

  return <div className="app-shell">
    <AppHeader run={run} busy={busy} onReset={run ? reset : undefined} onDelete={canDelete ? remove : undefined} deleteArmed={deleteArmed} />
    <main id="main-content" tabIndex={-1}>
      <div className="page-heading">
        <p className="eyebrow">{transport.dataSourceLabel ?? 'Public API'}{run ? '' : ' · no run loaded'}</p>
        {title ? <p>{title}</p> : null}
        <StepNavigation active={active} available={available} onNavigate={setActive}/>
      </div>
      {run ? <div className="status-strip" role="status"><strong>{statusLabel(run)}</strong>{isPollingStage(run.stage) ? <span>Partial results may change</span> : null}</div> : null}
      {deleteArmed && run ? <section className="panel" aria-label="Delete run confirmation"><p>Delete this run and its retained server data? This cannot be undone.</p><button type="button" className="secondary" disabled={busy} onClick={()=>setDeleteArmed(false)}>Cancel deletion</button></section> : null}
      <ErrorPanel error={error ?? run?.error}/>
      {error && lifecycle.runId ? <button type="button" className="secondary" disabled={busy} onClick={()=>void lifecycle.refresh()}>Refresh run</button> : null}
      {busy && !run ? <div role="status"><p>Loading run…</p><button type="button" className="secondary" onClick={reset}>Cancel loading</button><p className="muted small">Cancelling stops waiting locally; it does not delete a server run.</p></div> : null}
      {historical ? <p className="notice">Retained public snapshot from this session. Actions apply only to the current review.</p> : null}
      {run && currentStep !== 'input' && !snapshots.input ? <p className="muted small">Earlier detail is unavailable in this session. Only retained public snapshots can be reopened.</p> : null}
      {active === 'input' ? <InputContractView key={run?.run_id ?? 'new'} run={display} busy={busy || historical} onCreate={create} onConfirm={request=>void lifecycle.confirmContract(request)}/> : null}
      {active === 'evidence' && display ? <RunEvidenceView run={display}/> : null}
      {active === 'findings' && display ? <FindingsRevisionView key={run?.run_id} run={display} busy={busy || historical} onSelect={request=>void lifecycle.selectFindings(request)} onConfirm={request=>void lifecycle.confirmRevision(request)}/> : null}
      {active === 'comparison' && display ? <ComparisonView run={display}/> : null}
    </main>
    <footer><span>PolicyFuzz · Public run evidence</span><span>Deterministic results describe this frozen suite.</span></footer>
  </div>;
}
