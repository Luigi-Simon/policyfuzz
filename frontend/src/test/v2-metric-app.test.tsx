import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { V2App } from '../v2/V2App';
import completed from '../../../contracts/v2/fixtures/completed-public-result.json';
import { validateResult } from '../v2/api';
import { MetricError } from '../v2/metric-api';
import { clarificationReview, metricPolicy, metricResult, metricReview, unscoredResult } from './v2-metric-fixture';

describe('v2 Metric review and run workflow', () => {
  it('requires review, displays the interpreted rules, then renders traceable test evidence', async () => {
    const loadMetricSample = vi.fn().mockResolvedValue(metricPolicy);
    const prepareMetric = vi.fn().mockResolvedValue(metricReview);
    const runMetric = vi.fn().mockResolvedValue(metricResult);
    render(<V2App loadMetricSample={loadMetricSample} prepareMetric={prepareMetric} runMetric={runMetric} />);
    const user = userEvent.setup();

    expect(screen.queryByRole('button', { name: 'Confirm rules and run tests' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Load transport claims example' }));
    expect(screen.getByLabelText('Policy title')).toHaveValue(metricPolicy.title);
    expect(screen.getByLabelText('Policy description', { exact: true })).toHaveValue(metricPolicy.description);
    expect(screen.getByLabelText('Personality seed', { exact: true })).toHaveValue(metricPolicy.agent_seed);
    expect(screen.getByLabelText('Stakeholder count')).toHaveValue(metricPolicy.agent_count);
    await user.click(screen.getByRole('button', { name: 'Review policy rules' }));

    expect(await screen.findByRole('heading', { name: 'Metric rule review' })).toBeInTheDocument();
    expect(screen.getByText(metricReview.clauses[0].text)).toBeInTheDocument();
    expect(screen.getByText(metricReview.goals[0].text)).toBeInTheDocument();
    expect(screen.getByText('SGD 100.00')).toBeInTheDocument();
    expect(screen.getByText('Paid claims only')).toBeInTheDocument();
    expect(screen.getByText(metricReview.assumptions[0])).toBeInTheDocument();
    expect(screen.getByText(metricReview.limitations[0])).toBeInTheDocument();
    expect(runMetric).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'Confirm rules and run tests' }));
    expect(await screen.findByRole('heading', { name: 'Metric test results' })).toBeInTheDocument();
    expect(runMetric).toHaveBeenCalledWith(metricPolicy, metricReview, expect.any(AbortSignal));
    expect(screen.getByText('50%')).toBeInTheDocument();
    expect(screen.getByText('Tested cases only; this is not the chance that a policy succeeds.')).toBeInTheDocument();
    expect(screen.getByText('Boundary')).toBeInTheDocument();
    expect(screen.getByText(metricResult.cases[0].plausibility)).toBeInTheDocument();
    expect(screen.getAllByText('The claim was submitted.')[0]).toBeInTheDocument();
    await user.click(screen.getAllByRole('link', { name: 'S1' })[0]);
    expect(document.getElementById('metric-trace-CASE1')).toHaveAttribute('open');
    expect(screen.getByText('Action-deletion reduction')).toBeInTheDocument();
    expect(screen.getByText('OLD2')).toBeInTheDocument();
    expect(screen.getAllByText('P2')).toHaveLength(2);
    expect(screen.getByText('J2')).toBeInTheDocument();
    expect(screen.getByText(metricResult.suite_sha256)).toBeInTheDocument();
    expect(screen.getByText('Stakeholder count controls Sandbox participants, independently of Metric test cases.')).toBeInTheDocument();
  });

  it('clears accepted rules and Metric evidence after any policy edit', async () => {
    render(<V2App
      loadMetricSample={vi.fn().mockResolvedValue(metricPolicy)}
      prepareMetric={vi.fn().mockResolvedValue(metricReview)}
      runMetric={vi.fn().mockResolvedValue(metricResult)}
    />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Load transport claims example' }));
    await user.click(screen.getByRole('button', { name: 'Review policy rules' }));
    await user.click(await screen.findByRole('button', { name: 'Confirm rules and run tests' }));
    await screen.findByRole('heading', { name: 'Metric test results' });

    await user.type(screen.getByLabelText('Policy description'), ' Edited.');
    expect(screen.queryByRole('heading', { name: 'Metric rule review' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Metric test results' })).not.toBeInTheDocument();
  });

  it('shows clarification without offering a run or pass state', async () => {
    const runMetric = vi.fn();
    render(<V2App
      loadMetricSample={vi.fn().mockResolvedValue(metricPolicy)}
      prepareMetric={vi.fn().mockResolvedValue(clarificationReview)}
      runMetric={runMetric}
    />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Load transport claims example' }));
    await user.click(screen.getByRole('button', { name: 'Review policy rules' }));

    expect((await screen.findAllByText('Needs clarification'))[0]).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Confirm rules and run tests' })).not.toBeInTheDocument();
    expect(screen.queryByText('Pass')).not.toBeInTheDocument();
    expect(runMetric).not.toHaveBeenCalled();
  });

  it('labels unsupported cases as unscored and a null rate as not scored', async () => {
    render(<V2App
      loadMetricSample={vi.fn().mockResolvedValue(metricPolicy)}
      prepareMetric={vi.fn().mockResolvedValue(metricReview)}
      runMetric={vi.fn().mockResolvedValue(unscoredResult)}
    />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Load transport claims example' }));
    await user.click(screen.getByRole('button', { name: 'Review policy rules' }));
    await user.click(await screen.findByRole('button', { name: 'Confirm rules and run tests' }));

    expect(await screen.findByText('Not scored')).toBeInTheDocument();
    expect(screen.getAllByText('Unscored')[0]).toBeInTheDocument();
    expect(screen.getByText('The executor does not support fare adjustments.')).toBeInTheDocument();
  });


  it('clears the other evidence stream before changing workflow', async () => {
    render(<V2App
      createRun={vi.fn().mockResolvedValue(validateResult(completed))}
      loadMetricSample={vi.fn().mockResolvedValue(metricPolicy)}
      prepareMetric={vi.fn().mockResolvedValue(metricReview)}
      runMetric={vi.fn().mockResolvedValue(metricResult)}
    />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Load synthetic example' }));
    await user.click(screen.getByRole('button', { name: 'Run fixture' }));
    await screen.findByRole('heading', { name: 'Sandbox evidence' });
    await user.click(screen.getByRole('button', { name: 'Load transport claims example' }));
    await user.click(screen.getByRole('button', { name: 'Review policy rules' }));
    expect(screen.queryByRole('heading', { name: 'Sandbox evidence' })).not.toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: 'Confirm rules and run tests' }));
    await screen.findByRole('heading', { name: 'Metric test results' });
    await user.click(screen.getByRole('button', { name: 'Run fixture' }));
    await screen.findByRole('heading', { name: 'Sandbox evidence' });
    expect(screen.queryByRole('heading', { name: 'Metric test results' })).not.toBeInTheDocument();
  });

  it('disables duplicate submissions, aborts on unmount, and keeps stale errors safe', async () => {
    let rejectReview: (error: Error) => void = () => {};
    const prepareMetric = vi.fn().mockImplementation(() => new Promise((_, reject) => { rejectReview = reject; }));
    const { unmount } = render(<V2App
      loadMetricSample={vi.fn().mockResolvedValue(metricPolicy)}
      prepareMetric={prepareMetric}
    />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Load transport claims example' }));
    await user.click(screen.getByRole('button', { name: 'Review policy rules' }));
    expect(screen.getByRole('button', { name: 'Reviewing rules…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Run fixture' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Reviewing rules…' }));
    expect(prepareMetric).toHaveBeenCalledTimes(1);
    rejectReview(new MetricError('PRIVATE_PROVIDER_TRACE'));
    expect(await screen.findByRole('alert')).not.toHaveTextContent('PRIVATE_PROVIDER_TRACE');

    await user.click(screen.getByRole('button', { name: 'Review policy rules' }));
    const signal = prepareMetric.mock.calls[1][1] as AbortSignal;
    unmount();
    expect(signal.aborted).toBe(true);
  });
});
