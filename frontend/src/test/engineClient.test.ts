import { afterEach, describe, expect, it, vi } from 'vitest';
import { createRun, reviseRun, EngineApiError } from '../api/engineClient';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('engineClient', () => {
  it('posts multipart createRun and returns JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ run_id: 'run_1', status: 'completed' }),
    });
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
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ run_id: 'run_1', status: 'completed', ir: { revision: 2 } }),
    });
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
});
