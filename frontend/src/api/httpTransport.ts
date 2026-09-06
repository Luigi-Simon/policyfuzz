import { apiBase } from './config';
import { PublicTransportError, safePublicError, type PolicyFuzzTransport } from './transport';
import type {
  ConfirmContractRequest,
  ConfirmRevisionRequest,
  CreateRunRequest,
  CreateRunResponse,
  RunView,
  SelectFindingsRequest,
} from './types';
import {
  PublicResponseValidationError,
  validateCreateRunResponse,
  validateDeleteRunResponse,
  validatePublicError,
  validateRunView,
} from './validateRunView';

export const HTTP_REQUEST_TIMEOUT_MS = 15_000;

const invalidResponse = () =>
  safePublicError('INTERNAL_ERROR', 'The public API returned an invalid response.');
const unavailable = () =>
  safePublicError('PROVIDER_UNAVAILABLE', 'The public API is unavailable.', true);

function normalizeBaseUrl(value: string): string {
  return value.replace(/\/$/, '');
}

function assertRunId(runId: string): void {
  if (runId.length < 1 || runId.length > 200) {
    throw safePublicError('INVALID_INPUT', 'The run identifier is invalid.');
  }
}

export class HttpTransport implements PolicyFuzzTransport {
  readonly dataSourceLabel = 'Public API';
  private readonly baseUrl: string;
  private readonly timeoutMs: number;

  constructor(baseUrl = apiBase, timeoutMs = HTTP_REQUEST_TIMEOUT_MS) {
    this.baseUrl = normalizeBaseUrl(baseUrl);
    this.timeoutMs = timeoutMs;
  }

  async createRun(request: CreateRunRequest, signal?: AbortSignal): Promise<CreateRunResponse> {
    const value = await this.request('/api/v1/runs', 'POST', 202, request, signal);
    return this.validateSuccess(validateCreateRunResponse, value);
  }

  async getRun(runId: string, signal?: AbortSignal): Promise<RunView> {
    return this.runRequest(runId, '', 'GET', undefined, signal);
  }

  async confirmContract(
    runId: string,
    request: ConfirmContractRequest,
    signal?: AbortSignal,
  ): Promise<RunView> {
    return this.runRequest(runId, '/confirm-contract', 'POST', request, signal);
  }

  async selectFindings(
    runId: string,
    request: SelectFindingsRequest,
    signal?: AbortSignal,
  ): Promise<RunView> {
    return this.runRequest(runId, '/select-findings', 'POST', request, signal);
  }

  async confirmRevision(
    runId: string,
    request: ConfirmRevisionRequest,
    signal?: AbortSignal,
  ): Promise<RunView> {
    return this.runRequest(runId, '/confirm-revision', 'POST', request, signal);
  }

  async deleteRun(runId: string, signal?: AbortSignal): Promise<void> {
    assertRunId(runId);
    const value = await this.request(`/api/v1/runs/${encodeURIComponent(runId)}`, 'DELETE', 200, undefined, signal);
    const result = this.validateSuccess(validateDeleteRunResponse, value);
    if (!result.deleted || result.run_id !== runId) throw invalidResponse();
  }

  private async runRequest(
    runId: string,
    suffix: string,
    method: 'GET' | 'POST',
    body: ConfirmContractRequest | SelectFindingsRequest | ConfirmRevisionRequest | undefined,
    signal?: AbortSignal,
  ): Promise<RunView> {
    assertRunId(runId);
    const value = await this.request(
      `/api/v1/runs/${encodeURIComponent(runId)}${suffix}`,
      method,
      200,
      body,
      signal,
    );
    const result = this.validateSuccess(validateRunView, value);
    if (result.run_id !== runId) throw invalidResponse();
    return result;
  }

  private validateSuccess<T>(validator: (value: unknown) => T, value: unknown): T {
    try {
      return validator(value);
    } catch (error) {
      if (error instanceof PublicResponseValidationError) throw invalidResponse();
      throw error;
    }
  }

  private async request(
    path: string,
    method: 'GET' | 'POST' | 'DELETE',
    expectedStatus: number,
    body: object | undefined,
    callerSignal?: AbortSignal,
  ): Promise<unknown> {
    callerSignal?.throwIfAborted();
    const controller = new AbortController();
    let timedOut = false;
    const onCallerAbort = () => controller.abort(callerSignal?.reason);
    callerSignal?.addEventListener('abort', onCallerAbort, { once: true });
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, this.timeoutMs);
    try {
      const init: RequestInit = { method, signal: controller.signal };
      if (body !== undefined) {
        init.headers = { 'Content-Type': 'application/json' };
        init.body = JSON.stringify(body);
      }
      const response = await fetch(`${this.baseUrl}${path}`, init);
      const text = await response.text();
      let value: unknown;
      try {
        value = JSON.parse(text);
      } catch {
        throw response.status === expectedStatus ? invalidResponse() : unavailable();
      }
      if (response.status !== expectedStatus) {
        throw this.parseError(value, response.status);
      }
      return value;
    } catch (error) {
      if (callerSignal?.aborted) throw new DOMException('The request was aborted.', 'AbortError');
      if (timedOut) throw unavailable();
      if (error instanceof PublicTransportError) throw error;
      throw unavailable();
    } finally {
      clearTimeout(timer);
      callerSignal?.removeEventListener('abort', onCallerAbort);
    }
  }

  private parseError(value: unknown, status: number): PublicTransportError {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return unavailable();
    const keys = Object.keys(value);
    if (keys.length !== 1 || keys[0] !== 'error') return unavailable();
    try {
      const publicError = validatePublicError((value as { error?: unknown }).error);
      return new PublicTransportError(publicError, status);
    } catch {
      return unavailable();
    }
  }
}
