import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { usePolicyFuzzRun } from '../state/usePolicyFuzzRun';
import { stageView, isPollingStage } from '../state/stageView';
import { makeRunView, makeAwaitingContractView } from './runViewFactory';
import { PublicTransportError, type PolicyFuzzTransport } from '../api/transport';
import type { RunView, CreateRunRequest } from '../api/types';

const view = (stage: RunView['stage'], run_id = 'run-1'): RunView => ({...makeRunView(stage),run_id});
const deferred = <T,>() => { let resolve!: (value:T)=>void; let reject!: (error:unknown)=>void; const promise = new Promise<T>((yes,no)=>{resolve=yes;reject=no;}); return {promise,resolve,reject}; };
const fake = (getRun = vi.fn().mockResolvedValue(view('queued'))): PolicyFuzzTransport => ({getRun, createRun:vi.fn().mockResolvedValue({run_id:'run-1'}), confirmContract:vi.fn(), selectFindings:vi.fn(), confirmRevision:vi.fn(), deleteRun:vi.fn().mockResolvedValue(undefined)});
const request:CreateRunRequest = {schema_version:'1.0',text:null,source_type:'bundled_sample',sample_id:'synthetic-travel',title:'Synthetic test',non_confidential_confirmed:true};
const flush = () => act(async()=>{await Promise.resolve();});
afterEach(()=>vi.useRealTimers());

describe('public stages',()=>{
 it.each([
 ['queued','input',true],['ingesting','input',true],['extracting','input',true],['awaiting_contract','input',false],['contract_rejected','input',false],
 ['generating_initial_tests','evidence',true],['provisional_execution','evidence',true],['targeting_coverage','evidence',true],['freezing_suite','evidence',true],['baseline_execution','evidence',true],['analyzing','evidence',true],['completed_no_findings','evidence',false],['coverage_limit_exceeded','evidence',false],
 ['awaiting_finding_review','findings',false],['drafting_revision','findings',true],['awaiting_revision_confirmation','findings',false],['completed_no_revision','findings',false],['revision_rejected','findings',false],
 ['applying_revision','comparison',true],['retesting','comparison',true],['complete','comparison',false],['failed','input',false],
 ] as const)('routes %s to real view %s and polling=%s',(stage,step,polls)=>{expect(stageView(view(stage))).toBe(step);expect(isPollingStage(stage)).toBe(polls);});
 it('routes failure by latest non-failed public event without manufacturing completion',()=>{
  expect(stageView({...view('failed'),events:[{schema_version:'1.0',artifact:null,error_id:null,timestamp:'2026-09-04T00:00:00Z',stage:'analyzing',action_summary:'Analysis started'},{schema_version:'1.0',artifact:null,error_id:null,timestamp:'2026-09-04T00:00:01Z',stage:'failed',action_summary:'Run failed'}]})).toBe('evidence');
 });
});

describe('bounded run lifecycle',()=>{
 it('waits 1500ms after GET settlement and never overlaps slow polls',async()=>{
  vi.useFakeTimers(); const first=deferred<RunView>(), second=deferred<RunView>();
  const get=vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise),transport=fake(get);
  const {result,unmount}=renderHook(()=>usePolicyFuzzRun(transport,'run-1'));
  await act(async()=>{await vi.advanceTimersByTimeAsync(5000);}); expect(get).toHaveBeenCalledTimes(1);
  await act(async()=>first.resolve(view('queued'))); expect(result.current.run?.stage).toBe('queued');
  await act(async()=>{await vi.advanceTimersByTimeAsync(1499);}); expect(get).toHaveBeenCalledTimes(1);
  await act(async()=>{await vi.advanceTimersByTimeAsync(1);}); expect(get).toHaveBeenCalledTimes(2);
  await act(async()=>{await vi.advanceTimersByTimeAsync(9000);}); expect(get).toHaveBeenCalledTimes(2);
  await act(async()=>second.resolve(view('awaiting_contract')));
  await act(async()=>{await vi.advanceTimersByTimeAsync(9000);}); expect(get).toHaveBeenCalledTimes(2);
  unmount(); expect(get.mock.calls[1][1].aborted).toBe(true);
 });
 it.each(['awaiting_contract','awaiting_finding_review','awaiting_revision_confirmation','complete','completed_no_findings','completed_no_revision','contract_rejected','revision_rejected','coverage_limit_exceeded','failed'] as const)('stops at %s',async(stage)=>{
  vi.useFakeTimers(); const get=vi.fn().mockResolvedValue(view(stage)); const transport=fake(get);
  const {unmount}=renderHook(()=>usePolicyFuzzRun(transport,'run-1')); await flush();
  await act(async()=>{await vi.advanceTimersByTimeAsync(10000);}); expect(get).toHaveBeenCalledTimes(1); unmount();
 });
 it('creates then gets the returned ID immediately',async()=>{
  const transport=fake(vi.fn().mockResolvedValue(view('awaiting_contract'))); const {result}=renderHook(()=>usePolicyFuzzRun(transport));
  await act(async()=>{await result.current.createRun(request);}); expect(transport.createRun).toHaveBeenCalledWith(request,expect.any(AbortSignal)); expect(transport.getRun).toHaveBeenCalledWith('run-1',expect.any(AbortSignal)); expect(result.current.run?.stage).toBe('awaiting_contract');
 });
 it('suppresses a delayed create after local cancellation and never fetches after unmount',async()=>{
  const created=deferred<{run_id:string}>(),transport=fake(); transport.createRun=vi.fn().mockReturnValue(created.promise);
  const {result,unmount}=renderHook(()=>usePolicyFuzzRun(transport)); let creating!:Promise<void>;
  act(()=>{creating=result.current.createRun(request);}); act(()=>result.current.reset());
  await act(async()=>{created.resolve({run_id:'stale'});await creating;}); expect(result.current.run).toBeNull(); expect(transport.getRun).not.toHaveBeenCalled(); expect(transport.deleteRun).not.toHaveBeenCalled();
  const next=deferred<{run_id:string}>(); transport.createRun=vi.fn().mockReturnValue(next.promise); act(()=>{creating=result.current.createRun(request);}); unmount(); await act(async()=>{next.resolve({run_id:'unmounted'});await creating;}); expect(transport.getRun).not.toHaveBeenCalled();
 });
 it('ignores an old GET when the initial run is replaced',async()=>{
  const old=deferred<RunView>(),get=vi.fn().mockReturnValueOnce(old.promise).mockResolvedValue(view('complete','new')); const transport=fake(get);
  const {result,rerender}=renderHook(({id})=>usePolicyFuzzRun(transport,id),{initialProps:{id:'old'}});
  rerender({id:'new'}); await flush(); expect(get.mock.calls[0][1].aborted).toBe(true);
  await act(async()=>old.resolve(view('queued','old'))); expect(result.current.run?.run_id).toBe('new');
 });
 it('survives StrictMode cleanup and schedules only the current generation',async()=>{
  vi.useFakeTimers(); const transport=fake(vi.fn().mockResolvedValue(view('queued')));
  const {result,unmount}=renderHook(()=>usePolicyFuzzRun(transport,'run-1'),{reactStrictMode:true}); await flush(); expect(result.current.run?.run_id).toBe('run-1');
  const initialCalls = vi.mocked(transport.getRun).mock.calls.length;
  expect(initialCalls).toBe(2);
  await act(async()=>{await vi.advanceTimersByTimeAsync(1500);}); expect(transport.getRun).toHaveBeenCalledTimes(initialCalls + 1); unmount();
  for (const call of vi.mocked(transport.getRun).mock.calls) expect(call[1]?.aborted).toBe(true);
 });
 it('retains the run after a failed deletion and clears it only after success',async()=>{
  const deleting=deferred<void>(),transport=fake(vi.fn().mockResolvedValue({...view('complete'),allowed_actions:['delete_run']})); transport.deleteRun=vi.fn().mockReturnValueOnce(deleting.promise).mockResolvedValueOnce(undefined);
  const {result}=renderHook(()=>usePolicyFuzzRun(transport,'run-1')); await flush(); let action!:Promise<void>; act(()=>{action=result.current.deleteRun();}); expect(result.current.run?.run_id).toBe('run-1');
  await act(async()=>{deleting.reject(new Error('private provider text'));await action;}); expect(result.current.run?.run_id).toBe('run-1'); expect(result.current.error?.message).not.toContain('private');
  await act(async()=>{await result.current.deleteRun();}); expect(result.current.run).toBeNull();
 });
});

describe('typed actions and retained snapshots',()=>{
 const contract = () => ({...makeAwaitingContractView(),run_id:'run-1'});
 const confirm = {schema_version:'1.0' as const,decision:'reject' as const,baseline_policy_id:null,baseline_policy_sha256:null,invariants:[],required_dimensions:[]};
 it('caches an action response before its mandatory fresh GET and waits for that GET before polling',async()=>{
  vi.useFakeTimers();const updated=deferred<RunView>(),get=vi.fn().mockResolvedValueOnce(contract()).mockReturnValueOnce(updated.promise).mockResolvedValue(view('awaiting_finding_review'));
  const transport=fake(get);transport.confirmContract=vi.fn().mockResolvedValue(view('generating_initial_tests'));
  const {result}=renderHook(()=>usePolicyFuzzRun(transport,'run-1'));await flush();let pending!:Promise<void>;
  act(()=>{pending=result.current.confirmContract(confirm);});await flush();expect(result.current.run?.stage).toBe('generating_initial_tests');expect(result.current.snapshots.input?.pending_confirmation?.kind).toBe('contract');
  expect(transport.confirmContract).toHaveBeenCalledWith('run-1',confirm,expect.any(AbortSignal));expect(get).toHaveBeenCalledTimes(2);
  await act(async()=>{await vi.advanceTimersByTimeAsync(9000);});expect(get).toHaveBeenCalledTimes(2);
  await act(async()=>{updated.resolve(view('analyzing'));await pending;});
  await act(async()=>{await vi.advanceTimersByTimeAsync(1499);});expect(get).toHaveBeenCalledTimes(2);
  await act(async()=>{await vi.advanceTimersByTimeAsync(1);});expect(result.current.run?.stage).toBe('awaiting_finding_review');expect(get).toHaveBeenCalledTimes(3);
 });
 it('ignores a delayed action after run replacement, including the action GET',async()=>{
  const action=deferred<RunView>(),get=vi.fn().mockResolvedValueOnce(contract()).mockResolvedValue(view('complete','new'));
  const transport=fake(get);transport.confirmContract=vi.fn().mockReturnValue(action.promise);
  const {result,rerender}=renderHook(({id})=>usePolicyFuzzRun(transport,id),{initialProps:{id:'run-1'}});await flush();let pending!:Promise<void>;act(()=>{pending=result.current.confirmContract(confirm);});
  rerender({id:'new'});await flush();await act(async()=>{action.resolve(view('generating_initial_tests'));await pending;});expect(result.current.run?.run_id).toBe('new');expect(get).toHaveBeenCalledTimes(2);expect(result.current.snapshots.input).toBeUndefined();
 });
 it('resynchronizes a 409 once and preserves its structured public error',async()=>{
  const error={schema_version:'1.0' as const,code:'INVALID_STATE' as const,message:'The run has advanced. Review the latest state.',retryable:false,error_id:'public-409'};
  const get=vi.fn().mockResolvedValueOnce(contract()).mockResolvedValue(view('completed_no_findings')),transport=fake(get);
  transport.confirmContract=vi.fn().mockRejectedValue(new PublicTransportError(error,409));
  const {result}=renderHook(()=>usePolicyFuzzRun(transport,'run-1'));await flush();await act(async()=>{await result.current.confirmContract(confirm);});
  expect(result.current.run?.stage).toBe('completed_no_findings');expect(result.current.error).toEqual(error);expect(get).toHaveBeenCalledTimes(2);
 });
 it('preserves the action conflict when resynchronization fails and recovers only on explicit refresh',async()=>{
  vi.useFakeTimers();
  const conflict={schema_version:'1.0' as const,code:'INVALID_STATE' as const,message:'The run has advanced. Review the latest state.',retryable:false,error_id:'conflict-original-409'};
  const refreshFailure={schema_version:'1.0' as const,code:'PROVIDER_UNAVAILABLE' as const,message:'The public API is unavailable.',retryable:true,error_id:'refresh-failed-503'};
  const retained=contract();
  const get=vi.fn().mockResolvedValueOnce(retained).mockRejectedValueOnce(new PublicTransportError(refreshFailure,503)).mockResolvedValueOnce(view('completed_no_findings'));
  const transport=fake(get);transport.confirmContract=vi.fn().mockRejectedValue(new PublicTransportError(conflict,409));
  const {result}=renderHook(()=>usePolicyFuzzRun(transport,'run-1'));await flush();
  await act(async()=>{await result.current.confirmContract(confirm);});
  expect(result.current.run).toEqual(retained);
  expect(result.current.error).toEqual(conflict);
  expect(result.current.busy).toBe(false);
  await act(async()=>{await vi.advanceTimersByTimeAsync(10000);});
  expect(get).toHaveBeenCalledTimes(2);
  await act(async()=>{await result.current.refresh();});
  expect(get).toHaveBeenCalledTimes(3);
  expect(result.current.run?.stage).toBe('completed_no_findings');
  expect(result.current.error).toBeNull();
 });
 it('requires both the matching confirmation kind and server action permission',async()=>{
  const transport=fake(vi.fn().mockResolvedValue({...contract(),allowed_actions:['delete_run']}));const {result}=renderHook(()=>usePolicyFuzzRun(transport,'run-1'));await flush();await act(async()=>{await result.current.confirmContract(confirm);});expect(transport.confirmContract).not.toHaveBeenCalled();
 });
 it('does not refresh or submit a second action while the first action is pending',async()=>{
  const slow=deferred<RunView>(),get=vi.fn().mockResolvedValue(contract()),transport=fake(get);transport.confirmContract=vi.fn().mockReturnValue(slow.promise);
  const {result,unmount}=renderHook(()=>usePolicyFuzzRun(transport,'run-1'));await flush();let pending!:Promise<void>;act(()=>{pending=result.current.confirmContract(confirm);});await act(async()=>{await result.current.refresh();await result.current.confirmContract(confirm);});expect(transport.confirmContract).toHaveBeenCalledTimes(1);expect(get).toHaveBeenCalledTimes(1);
  unmount();await act(async()=>{slow.resolve(view('contract_rejected'));await pending;});expect(get).toHaveBeenCalledTimes(1);
 });
 it('does not render arbitrary error-shaped objects as public messages',async()=>{
  const transport=fake(vi.fn().mockRejectedValue({publicError:{code:'INTERNAL_ERROR',message:'private stack trace'}}));const {result}=renderHook(()=>usePolicyFuzzRun(transport,'run-1'));await flush();expect(result.current.error?.message).not.toContain('private stack trace');
 });
});

describe('deletion races',()=>{
 it('aborts a pending poll and ignores its late result after successful deletion',async()=>{
  vi.useFakeTimers();const slow=deferred<RunView>(),get=vi.fn().mockResolvedValueOnce({...view('queued'),allowed_actions:['delete_run']}).mockReturnValueOnce(slow.promise),transport=fake(get);
  const {result}=renderHook(()=>usePolicyFuzzRun(transport,'run-1'));await flush();await act(async()=>{await vi.advanceTimersByTimeAsync(1500);});
  await act(async()=>{await result.current.deleteRun();});expect(get.mock.calls[1][1].aborted).toBe(true);await act(async()=>slow.resolve(view('awaiting_contract')));expect(result.current.run).toBeNull();await act(async()=>{await vi.advanceTimersByTimeAsync(5000);});expect(get).toHaveBeenCalledTimes(2);
 });
 it('does not issue duplicate deletion while the first deletion is pending',async()=>{
  const slow=deferred<void>(),transport=fake(vi.fn().mockResolvedValue({...view('complete'),allowed_actions:['delete_run']}));transport.deleteRun=vi.fn().mockReturnValue(slow.promise);
  const {result}=renderHook(()=>usePolicyFuzzRun(transport,'run-1'));await flush();let first!:Promise<void>,second!:Promise<void>;act(()=>{first=result.current.deleteRun();second=result.current.deleteRun();});
  expect(transport.deleteRun).toHaveBeenCalledTimes(1);await act(async()=>{slow.resolve();await first;await second;});expect(result.current.run).toBeNull();
 });
});
