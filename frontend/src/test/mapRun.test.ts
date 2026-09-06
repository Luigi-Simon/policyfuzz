import { describe, it, expect } from 'vitest';
import { buildRevisionInstruction, buildSeedText, mapRunToView } from '../api/mapRun';
import type { RunRecord, UiFinding } from '../api/types';

const fixture: RunRecord = {
  run_id: 'run_abc123',
  status: 'completed',
  message: 'ok',
  ir: {
    policy_id: 'pol_1',
    title: 'Phone policy',
    revision: 1,
    source: { document_id: 'doc_1', filename: 'policy.txt', text: 'Students must not use phones.' },
    open_questions: ['What about emergencies?'],
    conflicts: [],
    rules: [
      {
        id: 'R1',
        title: 'No phones',
        statement: 'Students must not use phones in class.',
        citations: [{ document_id: 'doc_1', section: '1', quote: 'Students must not use phones in class.' }],
        when: [{ field: 'actor.role', op: 'eq', value: 'student' }],
        then: [{ modality: 'must_not', action: 'use_phone' }],
      },
    ],
  },
  suite: {
    suite_id: 'suite_1',
    policy_id: 'pol_1',
    policy_revision: 1,
    scenarios: [
      {
        scenario_id: 'scn_1',
        kind: 'adversarial',
        title: 'Student uses phone',
        narrative: 'A student uses a phone during class.',
        facts: { 'actor.role': 'student', 'action.name': 'use_phone' },
        targeted_rule_ids: ['R1'],
        expected_outcome: 'violation',
      },
      {
        scenario_id: 'scn_2',
        kind: 'normal',
        title: 'Student studies',
        narrative: 'A student studies quietly.',
        facts: { 'actor.role': 'student', 'action.name': 'study' },
        targeted_rule_ids: ['R1'],
        expected_outcome: 'compliant',
      },
    ],
  },
  evaluation: {
    report_id: 'eval_1',
    policy_id: 'pol_1',
    policy_revision: 1,
    suite_id: 'suite_1',
    findings: [
      {
        finding_id: 'fnd_1',
        scenario_id: 'scn_1',
        verdict: 'fail',
        rule_ids: ['R1'],
        summary: 'Phone use violated the must_not obligation.',
        traces: [{ rule_id: 'R1', matched: true, detail: 'actor matched' }],
      },
      {
        finding_id: 'fnd_2',
        scenario_id: 'scn_2',
        verdict: 'pass',
        rule_ids: ['R1'],
        summary: 'Compliant study behavior.',
        traces: [],
      },
    ],
  },
  effectiveness: {
    report_id: 'eff_1',
    policy_id: 'pol_1',
    policy_revision: 1,
    score: 72,
    justification: 'One adversarial failure against phone use.',
    recommended_actions: [{ rule_ids: ['R1'], action: 'clarify', summary: 'Clarify emergency exceptions for phone use.' }],
    swarm_used: false,
  },
};

describe('mapRunToView', () => {
  it('maps engine RunRecord into UI rules, scenarios, and findings', () => {
    const view = mapRunToView(fixture);
    expect(view.runId).toBe('run_abc123');
    expect(view.score).toBe(72);
    expect(view.rules).toHaveLength(1);
    expect(view.rules[0].id).toBe('R1');
    expect(view.rules[0].quote).toContain('phones');
    expect(view.scenarios).toHaveLength(2);
    expect(view.scenarios[0].assertion).toBe('Failed');
    expect(view.scenarios[0].finding).toBe(0);
    expect(view.scenarios[1].assertion).toBe('Passed');
    expect(view.scenarios[1].finding).toBeNull();
    expect(view.findings).toHaveLength(1);
    expect(view.findings[0].title).toContain('Phone use');
    expect(view.findings[0].trace[0]).toContain('R1');
    expect(view.failCount).toBe(1);
    expect(view.passCount).toBe(1);
    expect(view.openQuestions).toEqual(['What about emergencies?']);
  });

  it('falls back to recommended actions when every scenario passes', () => {
    const allPass: RunRecord = {
      ...fixture,
      evaluation: {
        ...fixture.evaluation!,
        findings: fixture.evaluation!.findings.map((f) => ({ ...f, verdict: 'pass' as const })),
      },
    };
    const view = mapRunToView(allPass);
    expect(view.findings.length).toBeGreaterThan(0);
    expect(view.findings[0].title).toContain('emergency');
  });
});

describe('seed and revision helpers', () => {
  it('builds seed text from goals and assumptions', () => {
    const text = buildSeedText({
      goals: ['Keep meals under 100'],
      assumptions: [{ text: 'Claims are individual', source: 'owner', confirmed: true }],
    });
    expect(text).toContain('Goal 1: Keep meals under 100');
    expect(text).toContain('Assumption 1 (confirmed)');
  });

  it('builds a revision instruction from accepted findings', () => {
    const findings: UiFinding[] = [
      {
        title: 'Gap',
        type: 'Failure',
        level: 'Engine',
        scenario: 'scn_1',
        rule: 'R1',
        facts: 'facts',
        expected: 'expected',
        observed: 'observed failure',
        quote: 'quote',
        section: '1',
        before: 'before',
        after: 'tighten R1',
        draft: 'tighten R1',
        trace: [],
      },
    ];
    const instruction = buildRevisionInstruction(findings, [0], ['Intent stays']);
    expect(instruction).toContain('Fix finding "Gap"');
    expect(instruction).toContain('Intent 1: Intent stays');
  });
});
