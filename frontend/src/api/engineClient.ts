import { apiUrl } from './config';
import type { CreateRunInput, RunRecord } from './types';

export class EngineApiError extends Error {
  status: number;
  body: string;

  constructor(status: number, body: string) {
    super(body || `Engine request failed (${status})`);
    this.name = 'EngineApiError';
    this.status = status;
    this.body = body;
  }
}

async function parseJson<T>(response: Response): Promise<T> {
  const text = await response.text();
  if (!response.ok) {
    throw new EngineApiError(response.status, text || response.statusText);
  }
  if (!text) {
    throw new EngineApiError(response.status, 'Empty response from engine');
  }
  return JSON.parse(text) as T;
}

export async function checkHealth(): Promise<{ status: string; service?: string }> {
  const response = await fetch(apiUrl('/health'));
  return parseJson(response);
}

export async function createRun(input: CreateRunInput): Promise<RunRecord> {
  const form = new FormData();
  form.append('policy_text', input.policyText);
  if (input.seedText) form.append('seed_text', input.seedText);
  if (input.populationSize != null) form.append('population_size', String(input.populationSize));
  if (input.groups?.length) form.append('groups', input.groups.join(','));
  if (input.segments?.length) form.append('audience_json', JSON.stringify(input.segments));
  if (input.locale) form.append('locale', input.locale);

  const response = await fetch(apiUrl('/v1/runs'), {
    method: 'POST',
    body: form,
  });
  return parseJson<RunRecord>(response);
}

export async function getRun(runId: string): Promise<RunRecord> {
  const response = await fetch(apiUrl(`/v1/runs/${encodeURIComponent(runId)}`));
  return parseJson<RunRecord>(response);
}

export async function reviseRun(runId: string, instruction: string): Promise<RunRecord> {
  const response = await fetch(apiUrl(`/v1/runs/${encodeURIComponent(runId)}/revise`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ instruction }),
  });
  return parseJson<RunRecord>(response);
}

export async function rehearseRun(runId: string, swarm = true): Promise<RunRecord> {
  const qs = swarm ? '?swarm=true' : '';
  const response = await fetch(apiUrl(`/v1/runs/${encodeURIComponent(runId)}/rehearse${qs}`), {
    method: 'POST',
  });
  return parseJson<RunRecord>(response);
}
