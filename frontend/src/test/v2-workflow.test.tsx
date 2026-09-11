import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { WorkflowApp } from '../v2/WorkflowApp';
import { createWorkflow, validateWorkflow } from '../v2/workflow-api';
import fixture from './fixtures/v2-workflow.json';
import policy from './fixtures/v2-policy.json';
import prose from './fixtures/v2-policy-conditions.json';
import scenarios from './fixtures/v2-policy-scenarios.json';
import employment from './fixtures/v2-employment.json';
import { WorkflowEvidence } from '../v2/WorkflowEvidence';

const capabilities = async () => ({ fixture_available: true, live_available: false, live_detail: 'Configure live services.', max_test_budget: 12, max_live_stakeholders: 50 });
const sample = async () => policy;
afterEach(() => { vi.unstubAllGlobals(); window.history.replaceState(null, '', '/v2'); });

describe('assembled workflow', () => {
  it('renders employment thresholds and unscored exceptions without payment labels', () => {
    render(<WorkflowEvidence result={validateWorkflow(employment, 'fixture')}/>);
    expect(screen.getByText(/12 cases · 3 passed · 0 failed · 9 unscored/)).toBeInTheDocument();
    expect(screen.getAllByText(/Condition check/)).toHaveLength(9);
    expect(screen.getByText(/Combined workplace outcomes and exceptions/)).toBeInTheDocument();
    expect(screen.queryByText(/Participant paid:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/do not verify benefit eligibility/)).not.toBeInTheDocument();
  });
  it('renders planned scenarios as unexecuted and unscored', () => {
    render(<WorkflowEvidence result={validateWorkflow(scenarios, 'fixture')}/>);
    expect(screen.getByText(/Scenario planning · no execution/)).toBeInTheDocument();
    expect(screen.getByText(/exploratory questions, not executed tests/)).toBeInTheDocument();
    expect(screen.queryByText(/cases cover a bounded reimbursement model/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Participant paid:/)).not.toBeInTheDocument();
  });

  it.each(['completed', 'wrong-method', 'scored', 'trace'])('rejects falsified planned scenarios: %s', mutation => {
    const value: any = structuredClone(scenarios);
    if (mutation === 'completed') value.metric.status = 'completed';
    if (mutation === 'wrong-method') value.metric.generation_method = 'rule_templates';
    if (mutation === 'scored') value.metric.cases[0].verdict = 'pass';
    if (mutation === 'trace') value.metric.cases[0].trace = fixture.metric.cases[0].trace;
    expect(() => validateWorkflow(value, 'fixture')).toThrow('could not be verified');
  });
  it.each(['#metric-old-case', '#v2-message-old-message', '#v2-persona-old'])('clears obsolete evidence navigation when editing a new run: %s', async hash => {
    window.history.replaceState(null, '', `/v2${hash}`);
    render(<WorkflowApp capabilities={capabilities} sample={sample}/>);
    await userEvent.setup().type(screen.getByLabelText('Policy title'), 'New policy');
    expect(window.location.hash).toBe('');
  });

  it('preserves navigation to the policy form on edits', async () => {
    window.history.replaceState(null, '', '/v2#workflow-main');
    render(<WorkflowApp capabilities={capabilities} sample={sample}/>);
    await userEvent.setup().type(screen.getByLabelText('Policy title'), 'New policy');
    expect(window.location.hash).toBe('#workflow-main');
  });

  it('shows no participants when setup failed', () => {
    const value: any = structuredClone(fixture);
    Object.assign(value.sandbox, { status: 'failed', configured_stakeholder_count: 0, observed_stakeholder_count: 0, personas: [], messages: [], sources: [], errors: ['sandbox_execution_failed: stage=roster; code=roster_count.'] });
    render(<WorkflowEvidence result={value}/>);
    expect(screen.queryByText(/personas were generated using/)).not.toBeInTheDocument();
    expect(screen.getByText(/No participant profiles are available/)).toBeInTheDocument();
  });
  it('renders partial policy condition evidence without inventing payments', () => {
    render(<WorkflowEvidence result={validateWorkflow(prose, 'fixture')}/>);
    expect(screen.getByText(/Metric ran with partial coverage/)).toBeInTheDocument();
    expect(screen.getByText(/do not verify whole-policy compliance/)).toBeInTheDocument();
    expect(screen.getAllByText(/Condition check/)).toHaveLength(6);
    expect(screen.queryByText(/Participant paid:/)).not.toBeInTheDocument();
  });

  it.each(['completed', 'wrong-method', 'foreign-condition'])('rejects falsified policy-condition evidence: %s', mutation => {
    const value: any = structuredClone(prose);
    if (mutation === 'completed') value.metric.status = 'completed';
    if (mutation === 'wrong-method') value.metric.generation_method = 'rule_templates';
    if (mutation === 'foreign-condition') value.metric.cases[0].actions[0].condition_id = 'foreign';
    expect(() => validateWorkflow(value, 'fixture')).toThrow('could not be verified');
  });

  it('submits exact inputs, independent settings and shows all four stages with cited advice', async () => {
    const run = vi.fn().mockResolvedValue(validateWorkflow(fixture, 'fixture'));
    render(<WorkflowApp run={run} capabilities={capabilities} sample={sample}/>);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Load synthetic example' }));
    await user.clear(screen.getByLabelText('Policy description'));
    await user.type(screen.getByLabelText('Policy description'), '  Exact policy input.  ');
    await user.click(screen.getByRole('button', { name: 'Run fixture workflow' }));
    await screen.findByRole('heading', { name: 'Judge advice' });
    expect(run.mock.calls[0][0]).toMatchObject({ policy: { ...policy, description: '  Exact policy input.  ' }, mode: 'fixture', test_budget: 12, max_rounds: 2, sandbox_timeout_seconds: 480 });
    expect(screen.getByRole('heading', { name: 'Metric test cases' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Sandbox evidence' })).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'overlapping-approvals' })[0]).toHaveAttribute('href', '#metric-overlapping-approvals');
    expect(screen.getByRole('option', { name: 'Live MiroFish and Judge' })).toBeDisabled();
  });

  it('blocks repeat submissions and clears old results on input edits', async () => {
    const run = vi.fn().mockResolvedValueOnce(validateWorkflow(fixture, 'fixture')).mockImplementationOnce(() => new Promise(() => {}));
    render(<WorkflowApp run={run} capabilities={capabilities} sample={sample}/>);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Load synthetic example' }));
    await user.click(screen.getByRole('button', { name: 'Run fixture workflow' }));
    await screen.findByRole('heading', { name: 'Judge advice' });
    await user.type(screen.getByLabelText('Personality seed'), ' More commuters.');
    expect(screen.queryByRole('heading', { name: 'Judge advice' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Run fixture workflow' }));
    expect(screen.getByRole('button', { name: 'Running workflow…' })).toBeDisabled();
  });

  it.each([
    ['wrong mode', (r: any) => { r.execution_mode = 'live'; }],
    ['foreign evidence', (r: any) => { r.metric.run_id = 'foreign'; }],
    ['wrong counts', (r: any) => { r.metric.passed = 12; }],
    ['missing assertion', (r: any) => { r.metric.cases[0].assertions = []; }],
    ['forged citation', (r: any) => { r.judge.cons[0].citations[0].id = 'invented'; }],
    ['unfounded pilot', (r: any) => { r.judge.recommendation = 'consider_limited_pilot'; }],
    ['private source', (r: any) => { r.sandbox.original_records = []; }],
    ['missing stage', (r: any) => { r.stages.pop(); }],
    ['false complete', (r: any) => { r.stages[2].status = 'failed'; }],
    ['invented interaction', (r: any) => { r.judge.key_interactions[0].citations = [r.judge.key_interactions[0].citations[0]]; }],
  ])('rejects %s', (_label, mutate) => {
    const value = structuredClone(fixture); mutate(value);
    expect(() => validateWorkflow(value, 'fixture')).toThrow('could not be verified');
  });

  it('checks the returned policy against the submitted exact text', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => fixture }));
    await expect(createWorkflow({ policy: { ...policy, description: 'Different policy.' }, mode: 'fixture', fixture_name: 'completed', max_rounds: 2, sandbox_timeout_seconds: 240, test_budget: 12 }, new AbortController().signal)).rejects.toThrow('does not match');
  });
});
