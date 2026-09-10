import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { MockTransport } from '../api/mockTransport';
import type { AgentSimulationResult, PolicyFuzzTransport } from '../api/transport';
import { makeRunView } from './runViewFactory';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function agentTransport() {
  return Object.assign(new MockTransport(), { supportsAgentSimulation: true });
}
async function startPolicy(transport: PolicyFuzzTransport) {
  const user = userEvent.setup();
  render(<App transport={transport} />);
  await user.type(screen.getByLabelText('Policy title'), 'Synthetic travel policy');
  await user.type(screen.getByLabelText('Policy text'), 'Employees can claim meals with receipts.');
  await user.click(screen.getByLabelText(/I confirm this policy is non-confidential/));
  await user.click(screen.getByLabelText(/Enable AI agents/i));
  await user.click(screen.getByRole('button', { name: 'Analyze policy' }));
  await screen.findByRole('heading', { name: 'Confirm policy contract' });
  for (const box of screen.getAllByRole('checkbox', { name: /Acknowledge rule|Confirm required dimension/ })) await user.click(box);
  await user.click(screen.getByRole('button', { name: 'Confirm policy contract' }));
  return user;
}
afterEach(() => { window.history.replaceState(null, '', '/'); vi.restoreAllMocks(); });

describe('independent simulation lifecycle', () => {
  it('aborts waiting on reset and ignores late results from the previous policy', async () => {
    const pending = deferred<AgentSimulationResult>();
    const transport = agentTransport();
    const simulate = vi.spyOn(transport, 'startAgentSimulation').mockReturnValue(pending.promise);
    const user = await startPolicy(transport);
    await waitFor(() => expect(simulate).toHaveBeenCalledOnce());
    const signal = simulate.mock.calls[0][1];
    await user.click(screen.getByRole('button', { name: 'New run' }));
    expect(signal?.aborted).toBe(true);
    await act(async () => pending.resolve({ run_id: 'stale-agent-run', status: 'completed' }));
    expect(screen.queryByText('stale-agent-run')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Policy input' })).toBeVisible();
  });

  it('deletes a policy without retaining its completed agent result', async () => {
    const transport = agentTransport();
    vi.spyOn(transport, 'startAgentSimulation').mockResolvedValue({ run_id: 'agent-to-delete', status: 'completed' });
    const user = await startPolicy(transport);
    await screen.findAllByText('agent-to-delete');
    await user.click(screen.getByRole('button', { name: 'Delete run' }));
    await user.click(screen.getByRole('button', { name: 'Confirm delete' }));
    await waitFor(() => expect(screen.queryAllByText('agent-to-delete')).toHaveLength(0));
    expect(new URL(window.location.href).searchParams.has('run_id')).toBe(false);
  });

  it('requires a separate exploratory action after extraction failure and keeps the original failure visible', async () => {
    const transport = agentTransport();
    const failed = { ...makeRunView('failed'), error: { schema_version: '1.0' as const, code: 'MALFORMED_MODEL_OUTPUT' as const, message: 'The policy extraction could not be validated.', retryable: false, error_id: 'extract-failed' } };
    vi.spyOn(transport, 'getRun').mockResolvedValue(failed);
    const generic = vi.fn().mockResolvedValue({ run_id: 'independent-run', status: 'completed' });
    Object.assign(transport, { startCustomAgentSimulation: generic });
    const user = userEvent.setup();
    render(<App transport={transport} />);
    await user.type(screen.getByLabelText('Policy title'), 'General policy');
    await user.type(screen.getByLabelText('Policy text'), 'Synthetic general policy prose.');
    await user.click(screen.getByLabelText(/I confirm this policy is non-confidential/));
    await user.click(screen.getByLabelText(/Enable AI agents/i));
    await user.click(screen.getByRole('button', { name: 'Analyze policy' }));
    await screen.findByText('The policy extraction could not be validated.');
    expect(generic).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Start independent exploratory simulation' }));
    await screen.findAllByText('independent-run');
    expect(screen.getByText('The policy extraction could not be validated.')).toBeVisible();
    expect(screen.queryByText('Agent simulation complete')).not.toBeInTheDocument();
  });

  it('keeps unknown simulation errors private', async () => {
    const transport = agentTransport();
    vi.spyOn(transport, 'startAgentSimulation').mockRejectedValue(new Error('private-provider-token'));
    await startPolicy(transport);
    expect(await screen.findByRole('alert')).not.toHaveTextContent('private-provider-token');
  });

  it('cancels a stored result on reset even when its transport resolves after cancellation', async () => {
    const pending = deferred<AgentSimulationResult>();
    const load = vi.fn().mockReturnValue(pending.promise);
    const transport = Object.assign(agentTransport(), { loadAgentSimulation: load });
    const user = userEvent.setup();
    render(<App transport={transport} initialAgentRunId="stored-agent" />);
    await waitFor(() => expect(load).toHaveBeenCalledOnce());
    await user.click(screen.getByRole('button', { name: 'Cancel simulation waiting' }));
    expect(load.mock.calls[0][1].aborted).toBe(true);
    await act(async () => pending.resolve({ run_id: 'stored-agent', status: 'completed' }));
    expect(screen.queryByText('stored-agent')).not.toBeInTheDocument();
  });

  it('does not carry a queued simulation into a retry with agents disabled', async () => {
    const transport = agentTransport();
    const create = transport.createRun.bind(transport);
    vi.spyOn(transport, 'createRun').mockRejectedValueOnce(new Error('offline')).mockImplementation(create);
    const simulate = vi.spyOn(transport, 'startAgentSimulation');
    const user = userEvent.setup();
    render(<App transport={transport} />);
    await user.type(screen.getByLabelText('Policy title'), 'Synthetic travel policy');
    await user.type(screen.getByLabelText('Policy text'), 'Employees can claim meals with receipts.');
    await user.click(screen.getByLabelText(/I confirm this policy is non-confidential/));
    await user.click(screen.getByLabelText(/Enable AI agents/i));
    await user.click(screen.getByRole('button', { name: 'Analyze policy' }));
    await screen.findByRole('alert');
    await user.click(screen.getByLabelText(/Enable AI agents/i));
    await user.click(screen.getByRole('button', { name: 'Analyze policy' }));
    await screen.findByRole('heading', { name: 'Confirm policy contract' });
    for (const box of screen.getAllByRole('checkbox', { name: /Acknowledge rule|Confirm required dimension/ })) await user.click(box);
    await user.click(screen.getByRole('button', { name: 'Confirm policy contract' }));
    await screen.findByText('Awaiting finding review');
    expect(simulate).not.toHaveBeenCalled();
  });

  it('retains the normal run identifier for refresh and removes it on reset', async () => {
    const user = userEvent.setup();
    render(<App transport={new MockTransport()} />);
    await user.type(screen.getByLabelText('Policy title'), 'Refreshable run');
    await user.click(screen.getByLabelText('Bundled sample'));
    await user.click(screen.getByLabelText(/I confirm this policy is non-confidential/));
    await user.click(screen.getByRole('button', { name: 'Analyze policy' }));
    await screen.findByRole('heading', { name: 'Confirm policy contract' });
    expect(new URL(window.location.href).searchParams.get('run_id')).toBe('synthetic-mock-run-1');
    await user.click(screen.getByRole('button', { name: 'New run' }));
    expect(new URL(window.location.href).searchParams.has('run_id')).toBe(false);
  });
});
