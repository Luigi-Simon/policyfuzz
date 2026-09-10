import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import App from '../App';
import { MockTransport } from '../api/mockTransport';
import { InputContractView } from '../views/InputContractView';

describe('simulation capability and input boundaries', () => {
  it('does not offer live MiroFish in cached demo mode', () => {
    render(<App transport={new MockTransport()} />);
    expect(screen.queryByLabelText(/Enable AI agents/i)).not.toBeInTheDocument();
  });
  it('explains why MiroFish cannot be requested with a bundled sample', async () => {
    const user = userEvent.setup();
    render(<InputContractView busy={false} onCreate={vi.fn()} onConfirm={vi.fn()} onAgentSimulation={vi.fn()} />);
    await user.click(screen.getByLabelText('Bundled sample'));
    expect(screen.getByLabelText(/Enable AI agents/i)).toBeDisabled();
    expect(screen.getByText(/paste non-confidential policy text to enable/i)).toBeVisible();
  });
  it('rejects an empty agent seed before creating any policy or simulation run', async () => {
    const user = userEvent.setup();
    const create = vi.fn();
    const simulate = vi.fn();
    render(<InputContractView busy={false} onCreate={create} onConfirm={vi.fn()} onAgentSimulation={simulate} />);
    await user.type(screen.getByLabelText('Policy title'), 'Travel policy');
    await user.type(screen.getByLabelText('Policy text'), 'Synthetic meal policy.');
    await user.click(screen.getByLabelText(/I confirm this policy is non-confidential/));
    await user.click(screen.getByLabelText(/Enable AI agents/i));
    await user.clear(screen.getByLabelText('Agent seed'));
    await user.click(screen.getByRole('button', { name: 'Analyze policy' }));
    expect(create).not.toHaveBeenCalled();
    expect(simulate).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent(/seed/i);
  });
  it('rejects fractional agent counts even if form native validation is bypassed', async () => {
    const user = userEvent.setup();
    const create = vi.fn();
    const { container } = render(<InputContractView busy={false} onCreate={create} onConfirm={vi.fn()} onAgentSimulation={vi.fn()} />);
    await user.type(screen.getByLabelText('Policy title'), 'Travel policy');
    await user.type(screen.getByLabelText('Policy text'), 'Synthetic meal policy.');
    await user.click(screen.getByLabelText(/I confirm this policy is non-confidential/));
    await user.click(screen.getByLabelText(/Enable AI agents/i));
    fireEvent.change(screen.getByLabelText('Agent count'), { target: { value: '1.5' } });
    fireEvent.submit(container.querySelector('form')!);
    expect(create).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent(/whole number/i);
  });
});
