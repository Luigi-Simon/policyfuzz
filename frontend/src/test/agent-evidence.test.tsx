import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { AgentSimulationResult } from '../api/transport';
import { AgentEvidenceView } from '../views/AgentEvidenceView';

const result: AgentSimulationResult = {
  run_id: 'swarm-1', status: 'completed', policy_title: 'Travel policy',
  effectiveness: { score: 98, interaction_verified: true, justification: 'Agent-provided assessment.', metrics: { verdicts: { pass: { unsafe: 'nested' } } } },
  evaluation: { findings: [{ scenario_id: 'scenario-1', verdict: 'fail', summary: 'Receipt exception needs review.', rule_ids: ['R001'] }] },
  ir: { rules: [{ id: 'R001', statement: 'Receipts are required for travel.' }] },
  extra: { swarm: { posts: [{ agent: 'Traveller', text: 'What about a lost receipt?' }] } },
};

describe('AgentEvidenceView evidence boundaries', () => {
  it('labels findings as candidate observations and heuristic scores, not proven defects', () => {
    render(<AgentEvidenceView result={result} step="findings" />);
    expect(screen.getByText('Exploratory simulation — unverified')).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Candidate agent observations' })).toBeVisible();
    expect(screen.getByText('Heuristic score')).toBeVisible();
    expect(screen.getByText(/not deterministic verdicts/i)).toBeVisible();
    expect(screen.getByText('Receipt exception needs review.')).toBeVisible();
    expect(screen.getByText('Receipts are required for travel.')).toBeVisible();
    expect(screen.queryByText(/policy is currently too broad/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/ran 1 independent fuzz-agent scenarios/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Maju Forest scenario suite/i)).not.toBeInTheDocument();
  });

  it('does not invent domain recommendations for a named forest policy', () => {
    render(<AgentEvidenceView result={{ ...result, policy_title: 'Maju Forest policy' }} step="findings" />);
    expect(screen.queryByText(/30%|14-day|minimum notice period|eligible housing/)).not.toBeInTheDocument();
    expect(screen.getByText(/confirm the intended behavior/i)).toBeVisible();
  });

  it('never equates no findings with policy completeness', () => {
    render(<AgentEvidenceView result={{ run_id: 'empty', status: 'completed' }} step="findings" />);
    expect(screen.getByText(/No structured observations were returned/i)).toBeVisible();
    expect(screen.queryByText(/tested cases behaved as expected/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Source policy text was not included/i)).toBeVisible();
  });

  it('reports missing frozen comparison despite high score and arbitrary provider metrics', () => {
    render(<AgentEvidenceView result={result} step="comparison" />);
    expect(screen.getByRole('heading', { name: 'No verified before-and-after comparison' })).toBeVisible();
    expect(screen.getByText(/frozen suite and baseline\/revised evaluation artifacts/i)).toBeVisible();
    expect(screen.getByText('Agent-provided assessment.')).toBeVisible();
    expect(screen.queryByText(/Final agent-backed effectiveness score/i)).not.toBeInTheDocument();
    expect(screen.queryByText('[object Object]')).not.toBeInTheDocument();
  });

  it('does not claim verified dialogue from a provider flag without returned replies', () => {
    render(<AgentEvidenceView result={result} />);
    expect(screen.getByText(/No reply\/comment records were returned/i)).toBeVisible();
    expect(screen.getAllByText('What about a lost receipt?').length).toBeGreaterThan(0);
    expect(screen.queryByText('Verified agent-to-agent replies from the MiroFish simulation.')).not.toBeInTheDocument();
  });

  it('retains returned replies without presenting the interaction flag as independent verification', () => {
    render(<AgentEvidenceView result={{ ...result, extra: { swarm: { comments: [{ user_name: 'Reviewer', content: 'Please clarify the exception.' }] } } }} />);
    expect(screen.getByText(/1 reply\/comment record returned/i)).toBeVisible();
    expect(screen.getAllByText('Please clarify the exception.').length).toBeGreaterThan(0);
    expect(screen.getByText(/not independently authenticated/i)).toBeVisible();
  });

  it('treats unusual provider verdict strings as labels without prototype-key corruption', () => {
    render(<AgentEvidenceView result={{ ...result, evaluation: { findings: [{ verdict: '__proto__', summary: 'Candidate only.' }] } }} step="findings" />);
    expect(screen.getByText('Candidate only.')).toBeVisible();
    expect(screen.getByText('__proto__')).toBeVisible();
  });

  it('does not show zero as a score when no independent assertions were scored', () => {
    render(<AgentEvidenceView result={{ ...result, effectiveness: { score: 0, metrics: { score_available: false, score_kind: 'exploratory_heuristic', unasserted_count: 10 } } }} />);
    expect(screen.getByText('Not scored')).toBeVisible();
    expect(screen.queryByText('0')).not.toBeInTheDocument();
  });

  it('discloses incomplete captures without echoing raw provider errors', () => {
    render(<AgentEvidenceView result={{ ...result, extra: { swarm: { error: 'private raw provider exception' } } }} />);
    expect(screen.getByText('Simulation capture may be incomplete.')).toBeVisible();
    expect(screen.queryByText('private raw provider exception')).not.toBeInTheDocument();
  });
});
