import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ComparisonView } from '../views/ComparisonView';
import { makeCompletedView } from './runViewFactory';

describe('ComparisonView', () => {
  it('never styles a rejected patch as success', () => {
    render(<ComparisonView run={makeCompletedView({ patchAccepted: false })} />);
    expect(screen.getByText('Revision did not pass all safeguards')).toHaveAttribute('data-tone', 'danger');
    expect(screen.queryByText('Safe to publish')).not.toBeInTheDocument();
  });

  it('renders six effect states, five transition categories, seven gates, and full input hashes', () => {
    const run = makeCompletedView();
    const comparison = run.comparison_metrics;
    if (!comparison) throw new Error('Expected completed comparison fixture');
    render(<ComparisonView run={run} />);

    expect(screen.getAllByRole('row', { name: /^Effect state (VALUE|GAP|NOT_APPLICABLE|CONFLICT|INCONCLUSIVE|ERROR)$/ })).toHaveLength(6);
    expect(screen.getAllByRole('row', { name: /^Assertion transition (fail_to_pass|fail_to_fail|pass_to_pass|pass_to_fail|inconclusive_or_error)$/ })).toHaveLength(5);
    expect(screen.getAllByRole('listitem', { name: /acceptance gate/i })).toHaveLength(7);
    for (const inputs of [comparison.acceptance.baseline_inputs, comparison.acceptance.revised_inputs]) {
      for (const value of Object.entries(inputs)) {
        if (value[0] !== 'schema_version') expect(screen.getAllByText(value[1])[0]).toBeVisible();
      }
    }
    expect(screen.getByText('Item-level transition IDs are unavailable in this public view.')).toBeVisible();
  });

  it('shows aggregate protected and holdout evidence without individual held-back cases', () => {
    const run = makeCompletedView();
    render(<ComparisonView run={run} />);

    const protectedMetric = screen.getByText('Protected regressions').parentElement;
    expect(protectedMetric).not.toBeNull();
    expect(within(protectedMetric!).getByText(`${run.comparison_metrics?.protected_regressions ?? 0}`)).toBeVisible();
    expect(screen.getByRole('region', { name: 'Aggregate holdout evidence' })).toBeVisible();
    expect(screen.queryByText(/held-back case/i)).not.toBeInTheDocument();
  });

  it('uses N/A for nullable percentages', () => {
    const base = makeCompletedView();
    const comparison = base.comparison_metrics;
    if (!comparison) throw new Error('Expected completed comparison fixture');
    const run = {
      ...base,
      comparison_metrics: {
        ...comparison,
        baseline: { ...comparison.baseline, assertion_pass_percent: null },
        revised: { ...comparison.revised, assertion_pass_percent: null },
      },
    };

    render(<ComparisonView run={run} />);
    expect(screen.getAllByText('N/A')).toHaveLength(2);
  });

  it('uses N/A rather than zero when baseline holdout states are absent', () => {
    const run = makeCompletedView();
    if (!run.holdout_evidence) throw new Error('Expected holdout evidence');
    delete run.holdout_evidence.baseline_effect_states;

    render(<ComparisonView run={run} />);
    const region = screen.getByRole('region', { name: 'Holdout effect state aggregates' });
    expect(screen.getByText('Baseline holdout effect-state counts are unavailable in this public snapshot.')).toBeVisible();
    expect(within(region).getAllByText('N/A')).toHaveLength(6);
  });
});
