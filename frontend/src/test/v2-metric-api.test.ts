import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  loadMetricSample,
  MetricError,
  prepareMetricReview,
  runMetricTests,
  validateMetricPolicy,
  validateMetricReview,
  validateMetricResult,
} from '../v2/metric-api';
import { metricPolicy, metricResult, metricReview } from './v2-metric-fixture';

afterEach(() => vi.unstubAllGlobals());

describe('v2 Metric response boundary', () => {
  it('rejects non-English public policy fields', () => {
    expect(() => validateMetricPolicy({ ...metricPolicy, title: '乘客' })).toThrow(
      'The Metric response could not be verified.',
    );
  });

  it('accepts a bound review and run from the canonical wire contract', () => {
    expect(validateMetricReview(structuredClone(metricReview))).toEqual(metricReview);
    expect(validateMetricResult(structuredClone(metricResult), metricReview)).toEqual(metricResult);
  });

  it.each([
    ['extra raw field', (value: any) => { value.raw_policy = 'private'; }],
    ['unknown category', (value: any) => { value.cases[0].category = 'surprise'; }],
    ['Han display text', (value: any) => { value.cases[0].plausibility = '乘客'; }],
    ['duplicate case ID', (value: any) => { value.cases[1].case_id = value.cases[0].case_id; }],
    ['wrong verdict counts', (value: any) => { value.passed = 2; }],
    ['wrong tested-case pass rate', (value: any) => { value.pass_rate = 1; }],
    ['unknown reviewed goal', (value: any) => { value.cases[0].assertions[0].requirement_id = 'MISSING'; }],
    ['unknown trace step', (value: any) => { value.cases[0].assertions[0].step_refs = ['MISSING']; }],
    ['unresolved trace action', (value: any) => { value.cases[0].trace[0].action_index = 3; }],
    ['invalid pass verdict', (value: any) => { value.cases[0].assertions[0].passed = false; }],
    ['Judge authored fixture result', (value: any) => { value.generation_method = 'authored_fixture'; }],
  ])('rejects %s', (_name, mutate) => {
    const value = structuredClone(metricResult);
    mutate(value);
    expect(() => validateMetricResult(value, metricReview)).toThrow(
      new MetricError('The Metric response could not be verified.'),
    );
  });

  it('rejects duplicate and unresolved review references', () => {
    const duplicate = structuredClone(metricReview);
    duplicate.clauses[1].id = duplicate.clauses[0].id;
    expect(() => validateMetricReview(duplicate)).toThrow('The Metric response could not be verified.');

    const unresolved = structuredClone(metricReview);
    unresolved.goals[0].clause_ids = ['MISSING'];
    expect(() => validateMetricReview(unresolved)).toThrow('The Metric response could not be verified.');
  });

  it('rejects a run bound to a different accepted review', () => {
    const stale = { ...metricReview, review_fingerprint: 'f'.repeat(64) };
    expect(() => validateMetricResult(metricResult, stale)).toThrow(
      'The Metric response could not be verified.',
    );
  });

  it('uses the additive endpoints and sends only the documented request fields', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(Response.json(metricPolicy))
      .mockResolvedValueOnce(Response.json(metricReview))
      .mockResolvedValueOnce(Response.json(metricResult));
    vi.stubGlobal('fetch', fetcher);
    const signal = new AbortController().signal;

    expect(await loadMetricSample(signal)).toEqual(metricPolicy);
    expect(await prepareMetricReview(metricPolicy, signal)).toEqual(metricReview);
    expect(await runMetricTests(metricPolicy, metricReview, signal)).toEqual(metricResult);
    expect(fetcher.mock.calls).toEqual([
      ['/api/v2/metric/sample', { signal }],
      ['/api/v2/metric/prepare', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ policy: metricPolicy }), signal,
      }],
      ['/api/v2/metric/runs', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ policy: metricPolicy, review_fingerprint: metricReview.review_fingerprint }), signal,
      }],
    ]);
  });

  it.each([
    [409, 'Policy inputs changed. Review the policy again.'],
    [422, 'Check the four policy fields and review the rules again.'],
    [502, 'The Metric service could not complete. Please retry.'],
  ])('maps HTTP %i to a fixed safe error', async (status, message) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('PRIVATE_PROVIDER_TRACE', { status })));
    await expect(runMetricTests(metricPolicy, metricReview, new AbortController().signal)).rejects.toThrow(message);
  });
});
