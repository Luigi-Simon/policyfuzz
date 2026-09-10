import { afterEach, describe, expect, it, vi } from 'vitest';
import completed from '../../../contracts/v2/fixtures/completed-public-result.json';
import partial from '../../../contracts/v2/fixtures/partial-translation-unavailable-public-result.json';
import { createFixtureRun, FixtureError, validateResult } from '../v2/api';

afterEach(() => vi.unstubAllGlobals());

describe('v2 public response boundary', () => {
  it('accepts completed, partial, failed and cancelled public results', () => {
    const failed = {
      ...structuredClone(completed),
      status: 'failed' as const,
      errors: ['Fixture execution failed.'],
    };
    const cancelled = structuredClone(completed);
    cancelled.status = 'cancelled';
    cancelled.limitations = ['Fixture execution was cancelled.'];

    expect(validateResult(completed).status).toBe('completed');
    expect(validateResult(partial).status).toBe('partial');
    expect(validateResult(failed).status).toBe('failed');
    expect(validateResult(cancelled).status).toBe('cancelled');
  });
  it.each([
    { ...completed, original_records: [] },
    { ...completed, messages: undefined },
    { ...completed, execution_mode: 'live' },
    { ...completed, observed_stakeholder_count: 2 },
    { ...partial, status: 'completed' },
    { ...completed, messages: [{ ...completed.messages[0], content: '原始记录' }, ...completed.messages.slice(1)] },
  ])('rejects malformed, private or mislabelled evidence', (value) => {
    expect(() => validateResult(value)).toThrow('The fixture response could not be verified.');
  });
  it('rejects a non-placeholder excerpt cited by an unavailable translation', () => {
    const value = structuredClone(partial);
    value.sources[1].excerpt = 'UNTRANSLATED ORIGINAL SOURCE';

    expect(() => validateResult(value)).toThrow(
      new FixtureError('The fixture response could not be verified.'),
    );
  });
  it.each([
    ['duplicate persona IDs', (value: typeof completed) => {
      value.status = 'partial';
      value.personas[1].persona_id = value.personas[0].persona_id;
      value.messages[1].persona_id = value.personas[0].persona_id;
      value.observed_stakeholder_count = 2;
    }],
    ['duplicate message IDs', (value: typeof completed) => {
      value.messages[1].message_id = value.messages[0].message_id;
      value.messages[1].source_refs = ['source-001'];
      value.sources.splice(1, 1);
    }],
    ['duplicate source IDs', (value: typeof completed) => {
      value.sources[1].source_id = value.sources[0].source_id;
      value.messages[1].source_refs = ['source-001'];
    }],
    ['duplicate source record IDs', (value: typeof completed) => {
      value.status = 'partial';
      value.sources[1].record_id = value.sources[0].record_id;
    }],
    ['a source with an unknown record', (value: typeof completed) => {
      value.status = 'partial';
      value.sources[0].record_id = 'missing-message';
    }],
    ['a message with an unknown persona', (value: typeof completed) => { value.messages[0].persona_id = 'missing-persona'; }],
    ['duplicate source references', (value: typeof completed) => { value.messages[0].source_refs = ['source-001', 'source-001']; }],
    ['an unknown source reference', (value: typeof completed) => { value.messages[0].source_refs = ['source-001', 'missing-source']; }],
    ['duplicate reply references', (value: typeof completed) => { value.messages[1].reply_to_message_ids = ['message-001', 'message-001']; }],
    ['an unknown reply reference', (value: typeof completed) => { value.messages[1].reply_to_message_ids = ['missing-message']; }],
    ['a reply to a later message', (value: typeof completed) => { value.messages[0].reply_to_message_ids = ['message-002']; }],
    ['non-contiguous message sequence', (value: typeof completed) => { value.messages[1].sequence = 3; }],
    ['a completed message without its own source', (value: typeof completed) => { value.messages[0].source_refs = ['source-002']; }],
  ])('rejects %s', (_name, mutate) => {
    const value = structuredClone(completed);
    mutate(value);

    expect(() => validateResult(value)).toThrow(
      new FixtureError('The fixture response could not be verified.'),
    );
  });
  it.each([
    { ...completed, status: 'failed' as const },
    { ...completed, status: 'partial' as const, limitations: [], errors: [] },
    { ...completed, status: 'cancelled' as const, limitations: [], errors: [] },
  ])('rejects a status without its required public explanation', (value) => {
    expect(() => validateResult(value)).toThrow(
      new FixtureError('The fixture response could not be verified.'),
    );
  });
  it('uses only the v2 endpoint and never displays a raw HTTP error', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('PRIVATE_POLICY_TEXT', { status: 502 }));
    vi.stubGlobal('fetch', fetcher);
    const signal = new AbortController().signal;
    const body = { policy: { title: 'Pilot', description: 'Synthetic policy', agent_seed: 'Practical', agent_count: 3 }, fixture_name: 'completed' as const };
    await expect(createFixtureRun(body, signal)).rejects.toThrow('The Sandbox fixture could not complete. Please retry.');
    expect(fetcher).toHaveBeenCalledWith('/api/v2/runs', expect.objectContaining({
      method: 'POST', body: JSON.stringify(body), signal,
    }));
  });
});
