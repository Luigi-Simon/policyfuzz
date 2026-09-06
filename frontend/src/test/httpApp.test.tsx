import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RunRecord } from '../api/types';

vi.mock('../api/config', () => ({
  isHttpMode: true,
  apiUrl: (path: string) => path,
}));

const engineMocks = vi.hoisted(() => ({
  createRun: vi.fn(),
  reviseRun: vi.fn(),
  rehearseRun: vi.fn(),
}));

vi.mock('../api/engineClient', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/engineClient')>();
  return { ...original, ...engineMocks };
});

import App from '../App';

const baselineRun: RunRecord = {
  run_id: 'run_baseline',
  status: 'completed',
  message: 'complete',
  ir: {
    policy_id: 'pol_1',
    title: 'Baseline policy',
    revision: 1,
    source: { document_id: 'doc_1', filename: 'policy.txt' },
    rules: [{ id: 'R1', title: 'Baseline rule', statement: 'Keep the baseline rule.' }],
    open_questions: [],
    conflicts: [],
  },
  suite: {
    suite_id: 'suite_baseline',
    policy_id: 'pol_1',
    policy_revision: 1,
    scenarios: [
      {
        scenario_id: 'scn_baseline',
        kind: 'normal',
        title: 'Baseline scenario',
        narrative: 'Baseline scenario facts remain visible.',
        expected_outcome: 'compliant',
      },
    ],
  },
  evaluation: {
    report_id: 'eval_1',
    policy_id: 'pol_1',
    policy_revision: 1,
    suite_id: 'suite_baseline',
    findings: [
      {
        finding_id: 'fnd_1',
        scenario_id: 'scn_baseline',
        verdict: 'pass',
        summary: 'Baseline passed.',
      },
    ],
  },
  effectiveness: {
    report_id: 'eff_1',
    policy_id: 'pol_1',
    policy_revision: 1,
    score: 72,
    justification: 'Baseline fuzz result.',
    recommended_actions: [],
    swarm_used: false,
  },
};

describe('HTTP adapter interface', () => {
  beforeEach(() => {
    engineMocks.createRun.mockReset();
    engineMocks.reviseRun.mockReset();
    engineMocks.rehearseRun.mockReset();
  });

  it('clears only the browser view and ignores a late create response', async () => {
    let finish!: (value: unknown) => void;
    engineMocks.createRun.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole('button', { name: 'Use sample policy' }));
    expect(engineMocks.createRun).toHaveBeenCalledOnce();
    expect(engineMocks.createRun.mock.calls[0][1]).toBeInstanceOf(AbortSignal);

    await user.click(screen.getByRole('button', { name: 'Clear view' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Server run data will remain in the engine store');
    await user.click(screen.getByRole('button', { name: 'Confirm clear' }));
    expect(engineMocks.createRun.mock.calls[0][1].aborted).toBe(true);

    await act(async () => {
      finish({
        run_id: 'late_run',
        status: 'completed',
        ir: null,
        suite: null,
        evaluation: null,
        effectiveness: null,
      });
    });

    expect(await screen.findByLabelText('Policy text')).toHaveValue('');
    expect(screen.queryByText(/late_run/)).not.toBeInTheDocument();
  });

  it('preserves the baseline when optional rehearsal returns a failed record', async () => {
    engineMocks.createRun.mockResolvedValue(baselineRun);
    engineMocks.rehearseRun.mockResolvedValue({
      run_id: 'run_baseline',
      status: 'failed',
      message: 'Pipeline failed',
      error: 'Traceback: private provider detail',
      ir: null,
      suite: null,
      evaluation: null,
      effectiveness: null,
    });
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole('checkbox', { name: /Explore interactions/ }));
    await user.click(screen.getByRole('button', { name: 'Use sample policy' }));
    await user.click(await screen.findByRole('checkbox', { name: /I confirm the extracted rules/ }));
    await user.click(screen.getByRole('button', { name: /Confirm contract & review results/ }));

    expect(await screen.findByText('Swarm rehearsal failed — using prior fuzz evaluation results')).toBeVisible();
    expect(screen.getByText('Baseline scenario facts remain visible.')).toBeVisible();
    expect(screen.getByText('72')).toBeVisible();
    expect(screen.queryByText(/private provider detail/)).not.toBeInTheDocument();
  });
});
