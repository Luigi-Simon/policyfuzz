import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import completed from '../../../contracts/v2/fixtures/completed-public-result.json';
import partial from '../../../contracts/v2/fixtures/partial-translation-unavailable-public-result.json';
import { V2App } from '../v2/V2App';
import { validateResult } from '../v2/api';

describe('v2 fixture flow', () => {
  it('submits four exact policy inputs and renders labelled, traceable evidence', async () => {
    const createRun = vi.fn().mockResolvedValue(validateResult(completed));
    render(<V2App createRun={createRun} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Load synthetic example' }));
    await user.clear(screen.getByLabelText('Policy description'));
    await user.type(screen.getByLabelText('Policy description'), '  Keep the exact policy text.  ');
    await user.click(screen.getByRole('button', { name: 'Run fixture' }));
    await screen.findByRole('heading', { name: 'Sandbox evidence' });
    expect(createRun).toHaveBeenCalledWith({
      policy: {
        title: 'Synthetic late-night transit pilot',
        description: '  Keep the exact policy text.  ',
        agent_seed: 'Include practical, safety-focused, and accessibility-focused voices.',
        agent_count: 3,
      },
      fixture_name: 'completed',
    }, expect.any(AbortSignal));
    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getAllByText('Synthetic fixture').length).toBeGreaterThan(0);
    expect(screen.getByText(completed.limitations[0])).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'Reply to message-001' })[0]).toHaveAttribute('href', '#v2-message-message-001');
    expect(screen.getByText(completed.request_fingerprint)).toBeInTheDocument();
    expect(screen.queryByText(/乘客/)).not.toBeInTheDocument();
  });

  it('keeps partial translation visibly incomplete and includes all limitations', async () => {
    const createRun = vi.fn().mockResolvedValue(validateResult(partial));
    render(<V2App createRun={createRun} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Load synthetic example' }));
    await user.selectOptions(screen.getByLabelText('Fixture sample'), 'partial_translation_unavailable');
    await user.click(screen.getByRole('button', { name: 'Run fixture' }));
    await screen.findByText('Partial — translation incomplete');
    expect(screen.queryByText('Completed')).not.toBeInTheDocument();
    expect(screen.getAllByText('[English translation unavailable for this record.]')).toHaveLength(2);
    expect(screen.getByText(partial.limitations[1])).toBeInTheDocument();
    expect(createRun.mock.calls[0][0].fixture_name).toBe('partial_translation_unavailable');
  });

  it('disables duplicate submission, clears old evidence and gives a safe retry', async () => {
    let rejectRun: (error: Error) => void = () => {};
    const createRun = vi.fn()
      .mockResolvedValueOnce(validateResult(completed))
      .mockImplementationOnce(() => new Promise((_, reject) => { rejectRun = reject; }));
    render(<V2App createRun={createRun} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Load synthetic example' }));
    await user.click(screen.getByRole('button', { name: 'Run fixture' }));
    await screen.findByRole('heading', { name: 'Sandbox evidence' });
    await user.click(screen.getByRole('button', { name: 'Run fixture' }));
    expect(screen.queryByRole('heading', { name: 'Sandbox evidence' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Running fixture…' })).toBeDisabled();
    rejectRun(new Error('PRIVATE_PROVIDER_TRACE'));
    expect(await screen.findByRole('alert')).not.toHaveTextContent('PRIVATE_PROVIDER_TRACE');
    expect(screen.getByRole('button', { name: 'Run fixture' })).toBeEnabled();
  });

  it('does not send whitespace-only input and aborts an unmounted request', async () => {
    const createRun = vi.fn().mockImplementation(() => new Promise(() => {}));
    const { unmount } = render(<V2App createRun={createRun} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Load synthetic example' }));
    await user.clear(screen.getByLabelText('Personality seed'));
    await user.type(screen.getByLabelText('Personality seed'), '   ');
    await user.click(screen.getByRole('button', { name: 'Run fixture' }));
    expect(createRun).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('Complete all four fields');
    await user.clear(screen.getByLabelText('Personality seed'));
    await user.type(screen.getByLabelText('Personality seed'), 'Practical voices');
    await user.click(screen.getByRole('button', { name: 'Run fixture' }));
    await waitFor(() => expect(createRun).toHaveBeenCalledTimes(1));
    const signal = createRun.mock.calls[0][1] as AbortSignal;
    unmount();
    expect(signal.aborted).toBe(true);
  });
});
