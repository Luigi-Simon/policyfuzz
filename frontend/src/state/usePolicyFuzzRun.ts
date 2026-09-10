import { useCallback, useEffect, useRef, useState } from 'react';
import { PublicTransportError, type PolicyFuzzTransport } from '../api/transport';
import type { ConfirmContractRequest, ConfirmRevisionRequest, CreateRunRequest, PublicError, RunView, SelectFindingsRequest } from '../api/types';
import { isPollingStage, retainSnapshot, type RunSnapshots } from './stageView';

const safeFailure: PublicError = {schema_version:'1.0',error_id:null,code:'INTERNAL_ERROR', message:'The request could not be completed. Please try again.', retryable:true};
// Only transport-validated public errors are displayed; arbitrary exceptions stay private.
function publicFailure(error: unknown): PublicError {
  if (error instanceof PublicTransportError) return error.publicError;
  return safeFailure;
}
function isConflict(error: unknown): boolean { return error instanceof PublicTransportError && error.status === 409; }

type Generation = {controller:AbortController; timer?:ReturnType<typeof setTimeout>; pending:boolean; deleting?:boolean};

export function usePolicyFuzzRun(transport: PolicyFuzzTransport, initialRunId?: string) {
  const [run, setRun] = useState<RunView|null>(null);
  const [snapshots, setSnapshots] = useState<RunSnapshots>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<PublicError|null>(null);
  const mounted = useRef(false);
  const generation = useRef<Generation|null>(null);
  const currentRun = useRef<RunView|null>(null);
  const currentId = useRef<string|undefined>(initialRunId);

  const invalidate = useCallback(() => {
    const old = generation.current;
    if (old?.timer !== undefined) clearTimeout(old.timer);
    old?.controller.abort();
    generation.current = null;
  }, []);
  const begin = useCallback(() => {
    invalidate();
    const next:Generation = {controller:new AbortController(), pending:false};
    generation.current = next;
    return next;
  }, [invalidate]);
  const current = useCallback((token:Generation) => mounted.current && generation.current === token && !token.controller.signal.aborted, []);
  const accept = useCallback((token:Generation, value:RunView) => {
    if (!current(token)) return;
    currentRun.current = value;
    currentId.current = value.run_id;
    setRun(value);
    setSnapshots(previous => retainSnapshot(previous, value));
  }, [current]);

  const getFresh = useCallback(async function getFresh(token:Generation, id:string, preserveError = false):Promise<void> {
    if (!current(token) || token.pending) return;
    if (token.timer !== undefined) clearTimeout(token.timer);
    token.timer = undefined;
    token.pending = true;
    try {
      const value = await transport.getRun(id, token.controller.signal);
      if (!current(token)) return;
      accept(token, value);
      if (isPollingStage(value.stage)) token.timer = setTimeout(() => {void getFresh(token, id);}, 1500);
    } catch (failure) {
      if (current(token) && !preserveError) setError(publicFailure(failure));
      // A failed request stops automatic polling. The explicit refresh can retry.
    } finally {
      token.pending = false;
      if (current(token)) setBusy(false);
    }
  }, [accept, current, transport]);

  const clearLocal = useCallback(() => {
    currentRun.current = null;
    currentId.current = undefined;
    setRun(null); setSnapshots({}); setError(null); setBusy(false);
  }, []);
  const reset = useCallback(() => {
    invalidate();
    if (mounted.current) clearLocal();
  }, [clearLocal, invalidate]);

  useEffect(() => {
    mounted.current = true;
    clearLocal();
    const token = begin();
    currentId.current = initialRunId;
    if (initialRunId) {setBusy(true); void getFresh(token, initialRunId);}
    return () => {mounted.current = false; invalidate();};
  }, [transport, initialRunId, begin, clearLocal, getFresh, invalidate]);

  const createRun = useCallback(async (request:CreateRunRequest):Promise<void> => {
    if (!mounted.current) return;
    const token = begin();
    clearLocal(); setBusy(true); token.pending = true;
    try {
      const created = await transport.createRun(request, token.controller.signal);
      if (!current(token)) return;
      currentId.current = created.run_id;
      token.pending = false;
      await getFresh(token, created.run_id);
    } catch (failure) {
      if (current(token)) setError(publicFailure(failure));
    } finally {token.pending = false; if (current(token)) setBusy(false);}
  }, [begin, clearLocal, current, getFresh, transport]);

  const action = useCallback(async (
    kind:'contract'|'findings'|'revision', allowed:NonNullable<RunView['allowed_actions']>[number],
    submit:(id:string, signal:AbortSignal)=>Promise<RunView>,
  ):Promise<void> => {
    const value = currentRun.current;
    if (!mounted.current || generation.current?.pending || !value || value.pending_confirmation?.kind !== kind || !value.allowed_actions?.includes(allowed)) return;
    const token = begin(); token.pending = true; setBusy(true); setError(null);
    try {
      const result = await submit(value.run_id, token.controller.signal);
      if (!current(token)) return;
      accept(token, result);
      token.pending = false;
      await getFresh(token, value.run_id);
    } catch (failure) {
      if (!current(token)) return;
      setError(publicFailure(failure));
      if (isConflict(failure)) {token.pending = false; await getFresh(token, value.run_id, true);}
    } finally {token.pending = false; if (current(token)) setBusy(false);}
  }, [accept, begin, current, getFresh]);

  const confirmContract = useCallback((request:ConfirmContractRequest) => action('contract', request.decision === 'reject' ? 'reject_contract' : 'confirm_contract', (id,signal)=>transport.confirmContract(id,request,signal)), [action,transport]);
  const selectFindings = useCallback((request:SelectFindingsRequest) => action('findings','select_findings',(id,signal)=>transport.selectFindings(id,request,signal)), [action,transport]);
  const confirmRevision = useCallback((request:ConfirmRevisionRequest) => action('revision',request.decision === 'reject' ? 'reject_revision' : 'confirm_revision',(id,signal)=>transport.confirmRevision(id,request,signal)), [action,transport]);
  const refresh = useCallback(async ():Promise<void> => {
    if (!mounted.current || generation.current?.pending || !currentId.current) return;
    const token = generation.current ?? begin();
    setError(null); setBusy(true);
    await getFresh(token, currentId.current);
  }, [begin,getFresh]);
  const deleteRun = useCallback(async (onDeleted?: () => void):Promise<void> => {
    const value = currentRun.current;
    if (!mounted.current || generation.current?.deleting || !value?.allowed_actions?.includes('delete_run')) return;
    const token = begin(); token.pending = true; token.deleting = true; setBusy(true); setError(null);
    try {
      await transport.deleteRun(value.run_id, token.controller.signal);
      if (current(token)) {invalidate(); clearLocal(); onDeleted?.();}
    } catch (failure) {if (current(token)) setError(publicFailure(failure));}
    finally {token.pending = false; token.deleting = false; if (current(token)) setBusy(false);}
  }, [begin,clearLocal,current,invalidate,transport]);

  return {run,runId:currentId.current,snapshots,busy,error,createRun,confirmContract,selectFindings,confirmRevision,deleteRun,refresh,reset};
}
