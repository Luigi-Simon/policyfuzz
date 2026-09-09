import { afterEach, describe, expect, it, vi } from 'vitest';
import { HttpTransport } from '../api/httpTransport';
import type { AgentSimulationRequest } from '../api/transport';
import { makeAwaitingFindingsView } from './runViewFactory';

const request: AgentSimulationRequest = { title: 'Synthetic', text: 'Meals need receipts.', seedText: 'Test expense cases', populationSize: 5, groups: 'employees,managers', confirmedRunId: 'synthetic-run' };
function readyTransport() {
  const transport = new HttpTransport();
  const run = makeAwaitingFindingsView();
  run.artifacts = ['policy_ir', 'policy_contract', 'scenario_suite'].map((kind) => ({
    schema_version: '1.0', title: kind, item_count: 1, artifact: { schema_version: '1.0', semantic_sha256: 'a'.repeat(64), artifact_type: kind as 'policy_ir', artifact_sha256: 'a'.repeat(64) },
  }));
  vi.spyOn(transport, 'getRun').mockResolvedValue(run);
  return transport;
}
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('bounded long-running independent simulation transport', () => {
  it('allows a valid simulation to outlast the normal 15-second API deadline', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn((_url, init: RequestInit) => new Promise<Response>((resolve, reject) => {
      setTimeout(() => resolve(new Response(JSON.stringify({ run_id: 'long-simulation', status: 'completed' }), { status: 200 })), 20_000);
      init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    })));
    let settled = false;
    const result = readyTransport().startAgentSimulation(request).then(value => { settled = true; return value; }, error => { settled = true; return error; });
    await vi.advanceTimersByTimeAsync(15_100);
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(5_000);
    expect(await result).toMatchObject({ run_id: 'long-simulation' });
  });
  it('still bounds a stalled simulation and honors caller cancellation', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn((_url, init: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    })));
    let settled = false;
    const result = readyTransport().startAgentSimulation(request).catch(error => { settled = true; return error; });
    await vi.advanceTimersByTimeAsync(359_999);
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    expect(await result).toMatchObject({ publicError: { code: 'PROVIDER_UNAVAILABLE' } });
    const controller = new AbortController();
    const cancelled = readyTransport().startAgentSimulation(request, controller.signal).catch(error => error);
    await vi.advanceTimersByTimeAsync(0);
    controller.abort();
    expect(await cancelled).toMatchObject({ name: 'AbortError' });
  });
});
