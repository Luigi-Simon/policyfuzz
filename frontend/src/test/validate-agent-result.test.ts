import { describe, expect, it } from 'vitest';
import { PublicTransportError } from '../api/transport';
import { validateAgentSimulationResult } from '../api/validateAgentResult';

const minimum = { run_id: 'simulation-1', status: 'completed' };

describe('agent simulation response validation', () => {
  it('accepts minimal responses and preserves unrendered extension data without mutation', () => {
    const value = { ...minimum, provider_extension: { future: [1, null, {}] }, error: null };
    expect(validateAgentSimulationResult(value)).toBe(value);
  });

  it('preserves failed engine records with explicitly null model sections', () => {
    // RunRecord.model_dump() emits null for artifacts that a failed stage never produced.
    const value = {
      run_id: 'failed-extraction', status: 'failed', message: 'Pipeline failed',
      error: 'The exploratory simulation did not complete.',
      document: null, ir: null, suite: null, evaluation: null,
      effectiveness: null, mirofish: null, extra: {},
    };
    const result = validateAgentSimulationResult(value);
    expect(result).toBe(value);
    expect(result.run_id).toBe('failed-extraction');
    expect(result.error).toBe(value.error);
  });

  it('accepts the optional public fields used in every evidence view', () => {
    const value = {
      ...minimum, compatibility_mode: 'custom', policy_title: 'Sample', policy_source_text: 'Synthetic text', message: 'Done',
      document: { filename: 'sample.txt', text: 'Sample text' },
      ir: { title: 'Sample', source: { text: 'Source' }, rules: [{ id: 'R001', statement: 'Receipts required.' }] },
      effectiveness: { score: 42, swarm_used: true, interaction_verified: false, justification: 'Tentative', metrics: { arbitrary: { nested: null } }, highlights: [{ agent: 'A', platform: 'sim', kind: 'post', text: 'Candidate', why_significant: 'Needs review' }] },
      evaluation: { findings: [{ scenario_id: 'S001', verdict: 'candidate', summary: 'Review', rule_ids: ['R001'], extra: {} }] },
      extra: { swarm: { interaction_verified: false, duplicate_messages_rejected: 2, error: 'Partial capture', posts: [{ agent: 'A', user_name: 'alice', text: 'Question', content: 'Question', arbitrary: null }], comments: [{ user_name: 'bob', content: 'Reply' }], actions: [{ agent_name: 'B', content: 'Action' }] } },
    };
    expect(validateAgentSimulationResult(value)).toBe(value);
  });

  it.each([
    null, [], 'raw provider error', {}, { run_id: 'run' }, { ...minimum, run_id: 7 }, { ...minimum, status: {} },
    { ...minimum, run_id: ' ' }, { ...minimum, status: '' },
    ...['compatibility_mode', 'policy_title', 'policy_source_text', 'message', 'error'].map((key) => ({ ...minimum, [key]: { secret: 'do not echo' } })),
    ...['document', 'ir', 'effectiveness', 'evaluation', 'extra'].map((key) => ({ ...minimum, [key]: [] })),
    { ...minimum, document: { text: {} } }, { ...minimum, ir: { source: null } },
    { ...minimum, ir: { rules: {} } }, { ...minimum, ir: { rules: [null] } }, { ...minimum, ir: { rules: [{ statement: {} }] } },
    { ...minimum, effectiveness: { score: '99' } }, { ...minimum, effectiveness: { score: NaN } }, { ...minimum, effectiveness: { score: Infinity } },
    { ...minimum, effectiveness: { interaction_verified: 'true' } }, { ...minimum, effectiveness: { justification: {} } },
    { ...minimum, effectiveness: { metrics: [] } }, { ...minimum, effectiveness: { highlights: [null] } }, { ...minimum, effectiveness: { highlights: [{ text: {} }] } },
    { ...minimum, evaluation: { findings: {} } }, { ...minimum, evaluation: { findings: [null] } }, { ...minimum, evaluation: { findings: [{ summary: {} }] } },
    { ...minimum, evaluation: { findings: [{ rule_ids: [12] }] } },
    { ...minimum, extra: { swarm: null } }, { ...minimum, extra: { swarm: { duplicate_messages_rejected: '2' } } },
    { ...minimum, extra: { swarm: { posts: {} } } }, { ...minimum, extra: { swarm: { comments: [null] } } },
    { ...minimum, extra: { swarm: { posts: [{ text: {} }] } } }, { ...minimum, extra: { swarm: { comments: [{ user_name: [] }] } } },
    { ...minimum, extra: { swarm: { actions: [{ agent_name: {} }] } } },
  ])('rejects malformed rendered response data safely (%#)', (value) => {
    try {
      validateAgentSimulationResult(value);
      expect.fail('Expected a safe validation error');
    } catch (error) {
      expect(error).toBeInstanceOf(PublicTransportError);
      expect((error as PublicTransportError).publicError).toMatchObject({ code: 'INTERNAL_ERROR', message: 'Agent simulation returned an invalid response.', retryable: false });
      expect(String(error)).not.toContain('do not echo');
    }
  });
});
