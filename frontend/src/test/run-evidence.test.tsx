import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { RunEvidenceView } from '../views/RunEvidenceView';
import { makeCompletedView, makeRunView } from './runViewFactory';

describe('RunEvidenceView', () => {
  it('renders only public events, measured coverage fractions, and separate result aggregates', () => {
    const run = makeCompletedView();
    render(<RunEvidenceView run={run} />);

    expect(screen.getByRole('heading', { name: 'Run evidence' })).toBeVisible();
    for (const event of run.events ?? []) expect(screen.getByText(event.action_summary)).toBeVisible();
    expect(screen.getByText(`${run.coverage?.covered_rules} / ${run.coverage?.total_rules}`)).toBeVisible();
    expect(screen.getByRole('region', { name: 'Effect state totals' })).toBeVisible();
    expect(screen.getByRole('region', { name: 'Assertion totals' })).toBeVisible();
    expect(screen.queryByText(/coverage lift/i)).not.toBeInTheDocument();
  });

  it('shows N/A for every zero-denominator coverage fraction', () => {
    render(<RunEvidenceView run={makeRunView('baseline_execution')} />);
    expect(screen.getAllByText('N/A')).toHaveLength(3);
  });

  it('does not turn an absent coverage projection into measured zeroes', () => {
    const run = makeCompletedView();
    delete run.coverage;
    render(<RunEvidenceView run={run} />);

    expect(screen.getByText('Coverage counters are unavailable in this public snapshot.')).toBeVisible();
    const region = screen.getByRole('region', { name: 'Measured coverage' });
    expect(within(region).getAllByText('N/A')).toHaveLength(4);
  });

  it('states when public run events are absent', () => {
    const run = makeCompletedView();
    run.events = [];
    render(<RunEvidenceView run={run} />);
    expect(screen.getByText('Public run events are unavailable in this snapshot.')).toBeVisible();
  });

  it('opens an accessible trace dialog with the public trace fields and full hash', async () => {
    const user = userEvent.setup();
    const run = makeCompletedView();
    const trace = run.traces?.[0];
    if (!trace) throw new Error('Completed fixture must include a visible trace');

    render(<RunEvidenceView run={run} />);
    const trigger = screen.getAllByRole('button', { name: /view trace/i })[0];
    await user.click(trigger);
    const dialog = screen.getByRole('dialog', { name: `Trace ${trace.scenario_id}` });

    expect(dialog).toBeVisible();
    expect(within(dialog).getByText(trace.trace_sha256)).toBeVisible();
    for (const ruleId of trace.fired_rule_ids) expect(within(dialog).getAllByText(ruleId)[0]).toBeVisible();
    expect(within(dialog).getByText('Scenario facts are unavailable in this public view.')).toBeVisible();
    expect(within(dialog).getByText('Individual assertion details are unavailable in this public view.')).toBeVisible();
    await user.click(within(dialog).getByRole('button', { name: 'Close trace' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it('shows visible rejection dispositions without reconstructing rejected content', () => {
    const run = makeCompletedView();
    render(<RunEvidenceView run={run} />);

    for (const rejection of run.rejections ?? []) {
      expect(screen.getByText(rejection.item_id)).toBeVisible();
      expect(screen.getAllByText(rejection.disposition.replaceAll('_', ' '))[0]).toBeVisible();
    }
  });
});
