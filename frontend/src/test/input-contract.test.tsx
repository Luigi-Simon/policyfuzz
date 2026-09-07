import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { InputContractView } from '../views/InputContractView';
import { makeAwaitingContractView } from './runViewFactory';

describe('InputContractView', () => {
  it('submits a valid pasted policy using the public create request', async () => {
    const user = userEvent.setup();
    const onCreate = vi.fn();

    render(<InputContractView busy={false} onCreate={onCreate} onConfirm={vi.fn()} />);
    await user.type(screen.getByLabelText('Policy title'), 'Meal policy');
    await user.type(screen.getByLabelText('Policy text'), 'Receipts are required for meal claims.');
    await user.click(screen.getByLabelText(/non-confidential/i));
    await user.click(screen.getByRole('button', { name: 'Analyze policy' }));

    expect(onCreate).toHaveBeenCalledWith({
      schema_version: '1.0',
      source_type: 'pasted_text',
      title: 'Meal policy',
      text: 'Receipts are required for meal claims.',
      sample_id: null,
      non_confidential_confirmed: true,
    });
  });

  it('queues agent configuration but still creates the normal Step 1 run', async () => {
    const user = userEvent.setup();
    const onCreate = vi.fn();
    const onAgentSimulation = vi.fn();

    render(<InputContractView busy={false} onCreate={onCreate} onConfirm={vi.fn()} onAgentSimulation={onAgentSimulation} />);
    await user.type(screen.getByLabelText('Policy title'), 'Forest policy');
    await user.type(screen.getByLabelText('Policy text'), 'The policy protects the forest and defines review safeguards.');
    await user.click(screen.getByLabelText(/non-confidential/i));
    await user.click(screen.getByLabelText(/Enable AI agents/i));
    await user.click(screen.getByRole('button', { name: 'Analyze policy' }));

    expect(onAgentSimulation).toHaveBeenCalledWith(expect.objectContaining({
      title: 'Forest policy',
      text: 'The policy protects the forest and defines review safeguards.',
    }));
    expect(onCreate).toHaveBeenCalledWith(expect.objectContaining({
      source_type: 'pasted_text',
      title: 'Forest policy',
      text: 'The policy protects the forest and defines review safeguards.',
    }));
  });

  it('rejects pasted text beyond the public 50,000-character limit', async () => {
    const user = userEvent.setup();
    const onCreate = vi.fn();

    render(<InputContractView busy={false} onCreate={onCreate} onConfirm={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('Policy title'), { target: { value: 'Long policy' } });
    fireEvent.change(screen.getByLabelText('Policy text'), { target: { value: 'x'.repeat(50_001) } });
    await user.click(screen.getByLabelText(/non-confidential/i));
    await user.click(screen.getByRole('button', { name: 'Analyze policy' }));

    expect(screen.getByRole('alert')).toHaveTextContent('Policy text must contain between 1 and 50,000 characters.');
    expect(onCreate).not.toHaveBeenCalled();
  });

  it('counts Unicode code points and accepts 50,000 astral characters', async () => {
    const user = userEvent.setup();
    const onCreate = vi.fn();
    const policy = '😀'.repeat(50_000);

    render(<InputContractView busy={false} onCreate={onCreate} onConfirm={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('Policy title'), { target: { value: 'Unicode policy' } });
    fireEvent.change(screen.getByLabelText('Policy text'), { target: { value: policy } });
    await user.click(screen.getByLabelText(/non-confidential/i));

    expect(screen.getByText('50,000 / 50,000 characters')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Analyze policy' }));
    expect(onCreate).toHaveBeenCalledWith(expect.objectContaining({ text: policy }));
  });

  it('submits the friendly bundled sample choice without a raw sample-ID field', async () => {
    const user = userEvent.setup();
    const onCreate = vi.fn();

    render(<InputContractView busy={false} onCreate={onCreate} onConfirm={vi.fn()} />);
    await user.click(screen.getByLabelText('Bundled sample'));
    fireEvent.change(screen.getByLabelText('Policy title'), { target: { value: 'Bundled sample' } });
    expect(screen.getByLabelText('Bundled policy sample')).toHaveDisplayValue('Development reimbursement policy');
    expect(screen.queryByLabelText('Bundled sample ID')).not.toBeInTheDocument();
    await user.click(screen.getByLabelText(/non-confidential/i));
    await user.click(screen.getByRole('button', { name: 'Analyze policy' }));

    expect(onCreate).toHaveBeenCalledWith(expect.objectContaining({
      source_type: 'bundled_sample',
      sample_id: 'development-policy',
      text: null,
    }));
  });

  it('keeps source fields before acknowledgement and submit in DOM order', () => {
    const { container } = render(<InputContractView busy={false} onCreate={vi.fn()} onConfirm={vi.fn()} />);
    const source = screen.getByLabelText('Policy text');
    const acknowledgement = screen.getByLabelText(/non-confidential/i);
    const submit = screen.getByRole('button', { name: 'Analyze policy' });

    expect(source.compareDocumentPosition(acknowledgement) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(acknowledgement.compareDocumentPosition(submit) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(container.querySelector('.input-grid > section')).toBeTruthy();
  });

  it('blocks confirmation with fewer than three selected invariants', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();

    render(
      <InputContractView
        run={makeAwaitingContractView(2)}
        busy={false}
        onCreate={vi.fn()}
        onConfirm={onConfirm}
      />,
    );
    await user.click(screen.getByRole('button', { name: 'Confirm policy contract' }));

    expect(screen.getByRole('alert')).toHaveTextContent('Confirm between 3 and 5 intent invariants.');
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('submits the exact baseline identifiers after every rule and dimension is acknowledged', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const run = makeAwaitingContractView(3);
    const pending = run.pending_confirmation;
    if (!pending || pending.kind !== 'contract') throw new Error('Expected contract fixture');

    render(<InputContractView run={run} busy={false} onCreate={vi.fn()} onConfirm={onConfirm} />);
    for (const checkbox of screen.getAllByRole('checkbox', { name: /acknowledge rule/i })) {
      await user.click(checkbox);
    }
    for (const checkbox of screen.getAllByRole('checkbox', { name: /confirm required dimension/i })) {
      await user.click(checkbox);
    }
    await user.click(screen.getByRole('button', { name: 'Confirm policy contract' }));

    expect(onConfirm).toHaveBeenCalledWith({
      schema_version: '1.0',
      decision: 'confirm',
      baseline_policy_id: pending.baseline_policy_id,
      baseline_policy_sha256: pending.baseline_policy_sha256,
      invariants: pending.invariants,
      required_dimensions: pending.required_dimensions,
    });
  });

  it('submits contract rejection without a confirmed baseline', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const run = makeAwaitingContractView(3);
    const pending = run.pending_confirmation;
    if (!pending || pending.kind !== 'contract') throw new Error('Expected contract fixture');

    render(<InputContractView run={run} busy={false} onCreate={vi.fn()} onConfirm={onConfirm} />);
    await user.click(screen.getByRole('button', { name: 'Reject policy contract' }));

    expect(onConfirm).toHaveBeenCalledWith({
      schema_version: '1.0',
      decision: 'reject',
      baseline_policy_id: null,
      baseline_policy_sha256: null,
      invariants: [],
      required_dimensions: [],
    });
  });

  it('disables every contract review control while busy or viewing history', () => {
    render(<InputContractView run={makeAwaitingContractView(3)} busy onCreate={vi.fn()} onConfirm={vi.fn()} />);
    for (const control of screen.getAllByRole('checkbox')) expect(control).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Reject policy contract' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Confirm policy contract' })).toBeDisabled();
  });
});
