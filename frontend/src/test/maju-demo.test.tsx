import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { MockTransport } from '../api/mockTransport';
import type { AgentSimulationRequest, AgentSimulationResult } from '../api/transport';
import { AgentEvidenceView } from '../views/AgentEvidenceView';

const notice = 'Hypothetical demo scenario — not a verified government announcement';
function simulationTransport() {
  return Object.assign(new MockTransport(), {
    supportsAgentSimulation: true,
    startCustomAgentSimulation: vi.fn<(request: AgentSimulationRequest, signal?: AbortSignal) => Promise<AgentSimulationResult>>().mockResolvedValue({ run_id: 'maju-exploration', status: 'completed' }),
  });
}
afterEach(() => { window.history.replaceState(null, '', '/'); vi.restoreAllMocks(); });

describe('Maju Forest exploratory demo', () => {
  it('loads a labelled hypothetical preset without submitting anything or granting consent', async () => {
    const transport = simulationTransport();
    const create = vi.spyOn(transport, 'createRun');
    render(<App transport={transport} />);
    await userEvent.click(screen.getByRole('button', { name: 'Use Maju Forest demo' }));
    expect(screen.getByRole('radio', { name: 'Exploratory stakeholder simulation' })).toBeChecked();
    expect(screen.getByLabelText('Policy title')).toHaveValue('Maju Forest Redevelopment and Land Optimization Framework');
    expect((screen.getByLabelText('Policy text') as HTMLTextAreaElement).value).toContain('32-hectare Maju Forest tract');
    expect(screen.getByText(notice)).toBeVisible();
    expect(screen.getByLabelText(/I confirm this policy is non-confidential/)).not.toBeChecked();
    expect(screen.getByLabelText(/I understand this sends the source/)).not.toBeChecked();
    expect(create).not.toHaveBeenCalled();
    expect(transport.startCustomAgentSimulation).not.toHaveBeenCalled();
  });

  it('requires external processing consent even after non-confidential confirmation', async () => {
    const transport = simulationTransport();
    render(<App transport={transport} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Use Maju Forest demo' }));
    await user.click(screen.getByLabelText(/I confirm this policy is non-confidential/));
    await user.click(screen.getByRole('button', { name: 'Start exploratory simulation' }));
    expect(screen.getByRole('alert')).toHaveTextContent(/external processing/i);
    expect(transport.startCustomAgentSimulation).not.toHaveBeenCalled();
  });

  it('launches directly with hypothetical context and editable stakeholder groups without creating a T&E run', async () => {
    const transport = simulationTransport();
    const create = vi.spyOn(transport, 'createRun');
    const confirmed = vi.spyOn(transport, 'startAgentSimulation');
    render(<App transport={transport} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Use Maju Forest demo' }));
    fireEvent.change(screen.getByLabelText('Stakeholder groups'), { target: { value: 'nearby residents, conservation researchers' } });
    await user.click(screen.getByLabelText(/I confirm this policy is non-confidential/));
    await user.click(screen.getByLabelText(/I understand this sends the source/));
    await user.click(screen.getByRole('button', { name: 'Start exploratory simulation' }));
    await screen.findAllByText('maju-exploration');
    expect(create).not.toHaveBeenCalled();
    expect(confirmed).not.toHaveBeenCalled();
    expect(transport.startCustomAgentSimulation).toHaveBeenCalledOnce();
    expect(transport.startCustomAgentSimulation.mock.calls[0][0]).toMatchObject({
      title: 'Maju Forest Redevelopment and Land Optimization Framework',
      text: expect.stringContaining(notice),
      groups: 'nearby residents, conservation researchers',
      populationSize: 5,
    });
    expect(transport.startCustomAgentSimulation.mock.calls[0][0].text).toContain('32-hectare Maju Forest tract');
    expect(transport.startCustomAgentSimulation.mock.calls[0][0].confirmedRunId).toBeUndefined();
    expect(new URL(window.location.href).searchParams.get('mirofish_run')).toBe('maju-exploration');
    expect(new URL(window.location.href).searchParams.has('run_id')).toBe(false);
    expect(screen.getByText(/does not reuse the frozen PolicyFuzz suite/)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Candidate observations' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Findings & revision' })).not.toBeInTheDocument();
    expect(screen.queryByText('Deterministic results describe this frozen suite.')).not.toBeInTheDocument();
  });

  it('locks input while waiting and aborts on New run without reviving late results', async () => {
    let resolve!: (result: AgentSimulationResult) => void;
    const transport = simulationTransport();
    transport.startCustomAgentSimulation.mockReturnValue(new Promise(done => { resolve = done; }));
    render(<App transport={transport} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Use Maju Forest demo' }));
    await user.click(screen.getByLabelText(/I confirm this policy is non-confidential/));
    await user.click(screen.getByLabelText(/I understand this sends the source/));
    await user.click(screen.getByRole('button', { name: 'Start exploratory simulation' }));
    await waitFor(() => expect(transport.startCustomAgentSimulation).toHaveBeenCalledOnce());
    expect(screen.getByLabelText('Policy text')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Starting…' })).toBeDisabled();
    const signal = transport.startCustomAgentSimulation.mock.calls[0][1];
    await user.click(screen.getByRole('button', { name: 'New run' }));
    expect(signal?.aborted).toBe(true);
    await act(async () => resolve({ run_id: 'late-maju-run', status: 'completed' }));
    expect(screen.queryByText('late-maju-run')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Policy title')).toHaveValue('');
    expect(screen.getByLabelText(/I confirm this policy is non-confidential/)).not.toBeChecked();
  });

  it('keeps the expense contract workflow available after selecting exploratory mode', async () => {
    const transport = simulationTransport();
    const create = vi.spyOn(transport, 'createRun');
    render(<App transport={transport} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('radio', { name: 'Exploratory stakeholder simulation' }));
    await user.click(screen.getByRole('radio', { name: 'Expense policy contract testing' }));
    await user.type(screen.getByLabelText('Policy title'), 'Expense demo');
    await user.click(screen.getByLabelText('Bundled sample'));
    await user.click(screen.getByLabelText(/I confirm this policy is non-confidential/));
    await user.click(screen.getByRole('button', { name: 'Analyze policy' }));
    await screen.findByRole('heading', { name: 'Confirm policy contract' });
    expect(create).toHaveBeenCalledOnce();
    expect(transport.startCustomAgentSimulation).not.toHaveBeenCalled();
  });

  it('does not offer external exploratory launch in authored mock mode', () => {
    render(<App transport={new MockTransport()} />);
    expect(screen.queryByRole('radio', { name: 'Exploratory stakeholder simulation' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Use Maju Forest demo' })).not.toBeInTheDocument();
  });

  it('keeps hypothetical and nonrepresentative labels visible on restored Maju evidence', () => {
    render(<AgentEvidenceView result={{ run_id: 'restored-maju', status: 'completed', policy_title: 'Maju Forest Redevelopment and Land Optimization Framework' }} />);
    expect(screen.getByText(notice)).toBeVisible();
    expect(screen.getByText(/not a representative survey or a prediction of public opinion/)).toBeVisible();
  });
});
