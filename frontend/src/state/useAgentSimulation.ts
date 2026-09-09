import { useCallback, useEffect, useRef, useState } from 'react';
import { PublicTransportError, safePublicError, type AgentSimulationRequest, type AgentSimulationResult, type PolicyFuzzTransport } from '../api/transport';

type AgentState = {
  busy: boolean;
  result?: AgentSimulationResult;
  error?: string;
  runId?: string;
  compatibility: boolean;
};
const emptyState: AgentState = { busy: false, compatibility: false };

/** Each request belongs to one local generation. Late provider responses never cross runs. */
export function useAgentSimulation(transport: PolicyFuzzTransport, initialRunId?: string) {
  const [state, setState] = useState<AgentState>({ ...emptyState, runId: initialRunId });
  const mounted = useRef(false);
  const generation = useRef<AbortController | null>(null);
  const invalidate = useCallback(() => {
    generation.current?.abort();
    generation.current = null;
  }, []);
  const reset = useCallback(() => {
    invalidate();
    if (mounted.current) setState(emptyState);
  }, [invalidate]);
  const perform = useCallback(async (operation: (signal: AbortSignal) => Promise<AgentSimulationResult>, compatibility: boolean, runId?: string) => {
    if (!mounted.current) return;
    invalidate();
    const controller = new AbortController();
    generation.current = controller;
    const current = () => mounted.current && generation.current === controller && !controller.signal.aborted;
    setState({ busy: true, compatibility, runId });
    try {
      const result = await operation(controller.signal);
      if (current()) setState({ busy: false, result, compatibility, runId: result.run_id });
    } catch (reason) {
      if (current()) setState({
        busy: false, compatibility, runId,
        error: reason instanceof PublicTransportError ? reason.publicError.message : 'The independent simulation could not be completed. Please try again.',
      });
    }
  }, [invalidate]);

  useEffect(() => {
    mounted.current = true;
    setState({ ...emptyState, runId: initialRunId });
    if (initialRunId) void perform(
      signal => transport.loadAgentSimulation
        ? transport.loadAgentSimulation(initialRunId, signal)
        : Promise.reject(safePublicError('PROVIDER_UNAVAILABLE', 'Stored agent evidence is unavailable in this mode.')),
      false,
      initialRunId,
    );
    return () => { mounted.current = false; invalidate(); };
  }, [initialRunId, invalidate, perform, transport]);

  const launch = useCallback((request: AgentSimulationRequest, compatibility = false) => perform(signal => {
    const starter = compatibility ? transport.startCustomAgentSimulation : transport.startAgentSimulation;
    if (!transport.supportsAgentSimulation || !starter) return Promise.reject(safePublicError('PROVIDER_UNAVAILABLE', 'Independent agent simulation is unavailable in this mode.'));
    return starter.call(transport, request, signal);
  }, compatibility), [perform, transport]);

  return { ...state, launch, reset };
}
