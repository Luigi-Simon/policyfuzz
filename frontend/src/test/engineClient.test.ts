import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  createRun,
  reviseRun,
  rehearseRun,
  EngineApiError,
  ENGINE_REQUEST_TIMEOUT_MS,
  EngineRequestTimeoutError,
  userFacingEngineError,
} from '../api/engineClient';
import type { RunRecord } from '../api/types';

const validRun: RunRecord = {
  run_id: 'run_1',
  status: 'completed',
  message: 'complete',
  ir: {
    policy_id: 'pol_1',
    title: 'Phone policy',
    revision: 1,
    source: { document_id: 'doc_1', filename: 'policy.txt' },
    rules: [
      {
        id: 'R1',
        title: 'No phones',
        statement: 'Students must not use phones.',
        citations: [{ document_id: 'doc_1', section: '1', quote: 'must not use phones' }],
        when: [{ field: 'actor.role', op: 'eq', value: 'student' }],
        then: [{ modality: 'must_not', action: 'use_phone' }],
      },
    ],
    open_questions: [],
    conflicts: [],
  },
  suite: {
    suite_id: 'suite_1',
    policy_id: 'pol_1',
    policy_revision: 1,
    scenarios: [
      {
        scenario_id: 'scn_1',
        kind: 'adversarial',
        title: 'Phone use',
        narrative: 'A student uses a phone.',
        facts: { 'actor.role': 'student' },
        targeted_rule_ids: ['R1'],
        expected_outcome: 'violation',
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
        summary: 'The rule failed.',
        traces: [{ rule_id: 'R1', matched: true, detail: 'matched' }],
      },
    ],
  },
  effectiveness: {
    report_id: 'eff_1',
    policy_id: 'pol_1',
    policy_revision: 1,
    score: 72,
    justification: 'One failure.',
    recommended_actions: [{ rule_ids: ['R1'], action: 'clarify', summary: 'Clarify the exception.' }],
    swarm_used: false,
  },
};

function response(body: unknown, overrides: Partial<Response> = {}): Response {
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    text: async () => JSON.stringify(body),
    ...overrides,
  } as Response;
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('engineClient', () => {
  it('posts multipart createRun and returns JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(validRun));
    vi.stubGlobal('fetch', fetchMock);

    const record = await createRun({
      policyText: 'Students must not use phones.',
      seedText: 'Goal 1: safety',
      groups: ['students'],
      segments: [{ id: 'students', label: 'Students' }],
      populationSize: 10,
    });

    expect(record.run_id).toBe('run_1');
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/v1/runs');
    expect(init.method).toBe('POST');
    expect(init.body).toBeInstanceOf(FormData);
    const form = init.body as FormData;
    expect(form.get('policy_text')).toBe('Students must not use phones.');
    expect(form.get('groups')).toBe('students');
  });

  it('posts JSON reviseRun', async () => {
    const revised = { ...validRun, ir: { ...validRun.ir!, revision: 2 } };
    const fetchMock = vi.fn().mockResolvedValue(response(revised));
    vi.stubGlobal('fetch', fetchMock);

    const record = await reviseRun('run_1', 'Exempt emergencies');
    expect(record.ir?.revision).toBe(2);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/v1/runs/run_1/revise');
    expect(init.headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(init.body)).toEqual({ instruction: 'Exempt emergencies' });
  });

  it('throws EngineApiError on non-OK responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        statusText: 'Unavailable',
        text: async () => 'engine down',
      }),
    );
    await expect(createRun({ policyText: 'x' })).rejects.toBeInstanceOf(EngineApiError);
  });

  it.each([
    ['an unknown run status', { ...validRun, status: 'done' }],
    ['a non-object policy IR', { ...validRun, ir: [] }],
    ['an invalid scenario kind', {
      ...validRun,
      suite: { ...validRun.suite!, scenarios: [{ ...validRun.suite!.scenarios[0], kind: 'random' }] },
    }],
    ['an invalid finding verdict', {
      ...validRun,
      evaluation: {
        ...validRun.evaluation!,
        findings: [{ ...validRun.evaluation!.findings[0], verdict: 'unknown' }],
      },
    }],
    ['a malformed nested trace', {
      ...validRun,
      evaluation: {
        ...validRun.evaluation!,
        findings: [{ ...validRun.evaluation!.findings[0], traces: [{ rule_id: 'R1', matched: 'yes' }] }],
      },
    }],
  ])('rejects a successful response containing %s', async (_label, body) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(body)));

    await expect(createRun({ policyText: 'x' })).rejects.toMatchObject({
      name: 'EngineApiError',
      kind: 'invalid-response',
    });
  });

  it('rejects a non-finite JSON number before mapping it', async () => {
    const raw = JSON.stringify(validRun).replace('"score":72', '"score":1e400');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(null, { text: async () => raw })));

    await expect(createRun({ policyText: 'x' })).rejects.toMatchObject({ kind: 'invalid-response' });
  });

  it.each([
    [
      'predicate value',
      (raw: string) => raw.replace('"value":"student"', '"value":{"nested":[null,{"overflow":1e400}]}'),
    ],
    [
      'scenario facts',
      (raw: string) =>
        raw.replace(
          '"facts":{"actor.role":"student"}',
          '"facts":{"actor.role":{"nested":[true,{"overflow":1e400}]}}',
        ),
    ],
  ])('rejects a non-finite number nested inside %s', async (_label, insertOverflow) => {
    const raw = insertOverflow(JSON.stringify(validRun));
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(null, { text: async () => raw })));

    await expect(createRun({ policyText: 'x' })).rejects.toMatchObject({ kind: 'invalid-response' });
  });

  it('accepts JSON-compatible predicate values and scenario facts', async () => {
    const run = structuredClone(validRun);
    run.ir!.rules[0].when![0].value = { nested: [null, true, 3.5, 'student'] };
    run.suite!.scenarios[0].facts = { nested: [{ enabled: false }, [1, 2, 3], null] };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(run)));

    await expect(createRun({ policyText: 'x' })).resolves.toMatchObject({ run_id: 'run_1' });
  });

  it.each([
    ['create', (signal: AbortSignal) => createRun({ policyText: 'x' }, signal)],
    ['revise', (signal: AbortSignal) => reviseRun('run_1', 'clarify', signal)],
    ['rehearse', (signal: AbortSignal) => rehearseRun('run_1', true, signal)],
  ])('passes caller cancellation through to %s requests', async (_label, request) => {
    let requestSignal: AbortSignal | undefined;
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init?: RequestInit) =>
        new Promise((_resolve, reject) => {
          requestSignal = init?.signal ?? undefined;
          requestSignal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
        }),
      ),
    );
    const controller = new AbortController();

    const pending = request(controller.signal);
    const rejected = expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    controller.abort();

    await rejected;
    expect(requestSignal?.aborted).toBe(true);
  });

  it('aborts an engine request at the fixed timeout bound', async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init?: RequestInit) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
        }),
      ),
    );

    const pending = createRun({ policyText: 'x' });
    const rejected = expect(pending).rejects.toBeInstanceOf(EngineRequestTimeoutError);
    await vi.advanceTimersByTimeAsync(ENGINE_REQUEST_TIMEOUT_MS);

    await rejected;
  });

  it('keeps raw backend details out of user-facing errors', () => {
    const error = new EngineApiError(500, 'Traceback: secret/path.py line 44\nprovider payload', 'http');

    expect(userFacingEngineError(error, 'Run')).toBe('Run failed (HTTP 500). Check the engine and try again.');
    expect(userFacingEngineError(error, 'Run')).not.toContain('Traceback');
  });
});
