import { afterEach, describe, expect, it, vi } from 'vitest';
import { HttpTransport } from '../api/httpTransport';
import { MockTransport } from '../api/mockTransport';
import { PublicTransportError } from '../api/transport';
import type {
  ConfirmContractRequest,
  ConfirmRevisionRequest,
  CreateRunRequest,
  RunView,
  SelectFindingsRequest,
} from '../api/types';
import {
  makeAwaitingContractView,
  makeAwaitingFindingsView,
  makeAwaitingRevisionView,
  makeCompletedView,
} from './runViewFactory';

const createRequest: CreateRunRequest = {
  schema_version: '1.0',
  source_type: 'bundled_sample',
  title: 'Synthetic sample',
  sample_id: 'synthetic-expense-policy',
  text: null,
  non_confidential_confirmed: true,
};

function response(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(body),
  } as Response;
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('MockTransport', () => {
  it('advances all three confirmations and returns isolated snapshots', async () => {
    const transport = new MockTransport();
    const { run_id } = await transport.createRun(createRequest);

    const contract = await transport.getRun(run_id);
    expect(contract.stage).toBe('awaiting_contract');
    contract.stage = 'failed';
    expect((await transport.getRun(run_id)).stage).toBe('awaiting_contract');

    const pendingContract = contract.pending_confirmation;
    expect(pendingContract?.kind).toBe('contract');
    if (pendingContract?.kind !== 'contract') throw new Error('expected contract');
    const contractRequest: ConfirmContractRequest = {
      schema_version: '1.0',
      decision: 'confirm',
      baseline_policy_id: pendingContract.baseline_policy_id,
      baseline_policy_sha256: pendingContract.baseline_policy_sha256,
      invariants: pendingContract.invariants,
      required_dimensions: pendingContract.required_dimensions,
    };
    expect((await transport.confirmContract(run_id, contractRequest)).stage).toBe('generating_initial_tests');
    const findings = await transport.getRun(run_id);
    expect(findings.stage).toBe('awaiting_finding_review');
    const pendingFindings = findings.pending_confirmation;
    if (pendingFindings?.kind !== 'findings') throw new Error('expected findings');
    const findingsRequest: SelectFindingsRequest = {
      schema_version: '1.0',
      decisions: [
        { finding_id: 'synthetic-finding-gap', decision: 'reject', reviewer_severity: null, schema_version: '1.0' },
        { finding_id: 'synthetic-finding-cap', decision: 'accept', reviewer_severity: null, schema_version: '1.0' },
      ],
    };
    expect((await transport.selectFindings(run_id, findingsRequest)).stage).toBe('drafting_revision');
    const revision = await transport.getRun(run_id);
    expect(revision.stage).toBe('awaiting_revision_confirmation');
    expect(revision.findings.find((item) => item.finding_id === 'synthetic-finding-gap')?.review_status).toBe('rejected');
    expect(revision.findings.find((item) => item.finding_id === 'synthetic-finding-cap')?.review_status).toBe('accepted');
    const pendingRevision = revision.pending_confirmation;
    if (pendingRevision?.kind !== 'revision') throw new Error('expected revision');
    const accepted = new Set(revision.findings.filter((item) => item.review_status === 'accepted').map((item) => item.finding_id));
    expect(pendingRevision.operations.flatMap((item) => item.operation.finding_ids).every((id) => accepted.has(id))).toBe(true);
    const revisionRequest: ConfirmRevisionRequest = {
      proposal_id: pendingRevision.proposal_id,
      decision: 'confirm',
      schema_version: '1.0',
    };
    expect((await transport.confirmRevision(run_id, revisionRequest)).stage).toBe('applying_revision');
    const completed = await transport.getRun(run_id);
    expect(completed).toMatchObject({ run_id, stage: 'complete', comparison_metrics: { patch_accepted: false } });
    expect(completed.findings.find((item) => item.finding_id === 'synthetic-finding-gap')?.review_status).toBe('rejected');
    expect(completed.findings.find((item) => item.finding_id === 'synthetic-finding-cap')?.review_status).toBe('accepted');
  });

  it('ends without a revision when every finding is rejected', async () => {
    const transport = new MockTransport();
    const { run_id } = await transport.createRun(createRequest);
    const contract = await transport.getRun(run_id);
    if (contract.pending_confirmation?.kind !== 'contract') throw new Error('expected contract');
    await transport.confirmContract(run_id, {
      decision: 'confirm',
      baseline_policy_id: contract.pending_confirmation.baseline_policy_id,
      baseline_policy_sha256: contract.pending_confirmation.baseline_policy_sha256,
      invariants: contract.pending_confirmation.invariants,
      required_dimensions: contract.pending_confirmation.required_dimensions,
      schema_version: '1.0',
    });
    const findings = await transport.getRun(run_id);
    if (findings.pending_confirmation?.kind !== 'findings') throw new Error('expected findings');
    const terminal = await transport.selectFindings(run_id, {
      decisions: findings.pending_confirmation.finding_ids.map((finding_id) => ({
        finding_id, decision: 'reject', reviewer_severity: null, schema_version: '1.0',
      })),
      schema_version: '1.0',
    });
    expect(terminal).toMatchObject({ stage: 'completed_no_revision', terminal_status: 'completed_no_revision' });
    expect(terminal.findings.every((finding) => finding.review_status === 'rejected')).toBe(true);
    expect(terminal.pending_confirmation).toBeNull();
    expect((await transport.getRun(run_id)).stage).toBe('completed_no_revision');
  });

  it('ends without inventing a proposal for an unsupported accepted-finding selection', async () => {
    const transport = new MockTransport();
    const { run_id } = await transport.createRun(createRequest);
    const contract = await transport.getRun(run_id);
    if (contract.pending_confirmation?.kind !== 'contract') throw new Error('expected contract');
    await transport.confirmContract(run_id, {
      decision: 'confirm',
      baseline_policy_id: contract.pending_confirmation.baseline_policy_id,
      baseline_policy_sha256: contract.pending_confirmation.baseline_policy_sha256,
      invariants: contract.pending_confirmation.invariants,
      required_dimensions: contract.pending_confirmation.required_dimensions,
      schema_version: '1.0',
    });
    const findings = await transport.getRun(run_id);
    const terminal = await transport.selectFindings(run_id, {
      decisions: [
        { finding_id: 'synthetic-finding-gap', decision: 'accept', reviewer_severity: 'medium', schema_version: '1.0' },
        { finding_id: 'synthetic-finding-cap', decision: 'reject', reviewer_severity: null, schema_version: '1.0' },
      ],
      schema_version: '1.0',
    });
    expect(terminal.stage).toBe('completed_no_revision');
    expect(terminal.pending_confirmation).toBeNull();
    expect(terminal.findings.find((item) => item.finding_id === 'synthetic-finding-gap')?.review_status).toBe('accepted');
  });

  it('rejects create and contract commands that violate public cross-field semantics', async () => {
    const transport = new MockTransport();
    await expect(transport.createRun({ ...createRequest, text: 'not allowed with a sample' })).rejects.toMatchObject({
      publicError: { code: 'INVALID_INPUT' },
    });
    await expect(transport.createRun({
      ...createRequest,
      source_type: 'pasted_text',
      sample_id: null,
      text: '   ',
    })).rejects.toMatchObject({ publicError: { code: 'INVALID_INPUT' } });

    const { run_id } = await transport.createRun(createRequest);
    const contract = await transport.getRun(run_id);
    if (contract.pending_confirmation?.kind !== 'contract') throw new Error('expected contract');
    const duplicated = contract.pending_confirmation.invariants.map((item) => structuredClone(item));
    duplicated[1].invariant_id = duplicated[0].invariant_id;
    await expect(transport.confirmContract(run_id, {
      decision: 'confirm',
      baseline_policy_id: contract.pending_confirmation.baseline_policy_id,
      baseline_policy_sha256: contract.pending_confirmation.baseline_policy_sha256,
      invariants: duplicated,
      required_dimensions: ['eligibility'],
      schema_version: '1.0',
    })).rejects.toMatchObject({ publicError: { code: 'INVALID_INPUT' } });
  });

  it('supports explicit rejection, alternate terminal state, abort, and deletion', async () => {
    const transport = new MockTransport({ terminalStage: 'completed_no_revision' });
    const { run_id } = await transport.createRun(createRequest);
    await transport.getRun(run_id);
    const contract = await transport.getRun(run_id);
    if (contract.pending_confirmation?.kind !== 'contract') throw new Error('expected contract');
    const rejected = await transport.confirmContract(run_id, {
      decision: 'reject',
      baseline_policy_id: null,
      baseline_policy_sha256: null,
      invariants: [],
      required_dimensions: [],
      schema_version: '1.0',
    });
    expect(rejected.terminal_status).toBe('contract_rejected');

    const controller = new AbortController();
    controller.abort();
    await expect(transport.getRun(run_id, controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
    await transport.deleteRun(run_id);
    await expect(transport.getRun(run_id)).rejects.toMatchObject({
      publicError: { code: 'RUN_NOT_FOUND' },
      status: 404,
    });
  });

  it('rejects commands that do not match the pending server-held state', async () => {
    const transport = new MockTransport();
    const { run_id } = await transport.createRun(createRequest);
    const contract = await transport.getRun(run_id);
    if (contract.pending_confirmation?.kind !== 'contract') throw new Error('expected contract');
    await expect(
      transport.confirmContract(run_id, {
        decision: 'confirm',
        baseline_policy_id: 'wrong',
        baseline_policy_sha256: contract.pending_confirmation.baseline_policy_sha256,
        invariants: contract.pending_confirmation.invariants,
        required_dimensions: contract.pending_confirmation.required_dimensions,
        schema_version: '1.0',
      }),
    ).rejects.toMatchObject({ publicError: { code: 'INVALID_STATE' }, status: 409 });
  });
});

describe('HttpTransport', () => {
  it('uses the exact public paths, methods, JSON bodies, statuses, and encoded run ID', async () => {
    const runId = 'run /one';
    const contract = { ...makeAwaitingContractView(), run_id: runId };
    const findings = { ...makeAwaitingFindingsView(), run_id: runId };
    const revision = { ...makeAwaitingRevisionView(), run_id: runId };
    const completed = { ...makeCompletedView(), run_id: runId };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(202, { run_id: runId, schema_version: '1.0' }))
      .mockResolvedValueOnce(response(200, contract))
      .mockResolvedValueOnce(response(200, findings))
      .mockResolvedValueOnce(response(200, revision))
      .mockResolvedValueOnce(response(200, completed))
      .mockResolvedValueOnce(response(200, { run_id: runId, deleted: true, schema_version: '1.0' }));
    vi.stubGlobal('fetch', fetchMock);
    const transport = new HttpTransport('https://public.example.test/');

    await transport.createRun(createRequest);
    await transport.getRun(runId);
    await transport.confirmContract(runId, {
      decision: 'reject', baseline_policy_id: null, baseline_policy_sha256: null,
      invariants: [], required_dimensions: [], schema_version: '1.0',
    });
    await transport.selectFindings(runId, {
      decisions: [{ finding_id: 'synthetic-finding-gap', decision: 'reject', reviewer_severity: null, schema_version: '1.0' }],
      schema_version: '1.0',
    });
    await transport.confirmRevision(runId, { proposal_id: 'synthetic-proposal-1', decision: 'reject', schema_version: '1.0' });
    await transport.deleteRun(runId);

    const prefix = 'https://public.example.test/api/v1/runs';
    expect(fetchMock.mock.calls.map(([url, init]) => [url, init.method])).toEqual([
      [prefix, 'POST'],
      [`${prefix}/run%20%2Fone`, 'GET'],
      [`${prefix}/run%20%2Fone/confirm-contract`, 'POST'],
      [`${prefix}/run%20%2Fone/select-findings`, 'POST'],
      [`${prefix}/run%20%2Fone/confirm-revision`, 'POST'],
      [`${prefix}/run%20%2Fone`, 'DELETE'],
    ]);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual(createRequest);
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({
      decision: 'reject', baseline_policy_id: null, baseline_policy_sha256: null,
      invariants: [], required_dimensions: [], schema_version: '1.0',
    });
  });

  it('rejects malformed successful data and mismatched run IDs', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(200, { ...makeCompletedView(), extra_private: true })));
    await expect(new HttpTransport().getRun('synthetic-completed-run')).rejects.toBeInstanceOf(PublicTransportError);

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(200, makeCompletedView())));
    await expect(new HttpTransport().getRun('different-run')).rejects.toMatchObject({
      publicError: { code: 'INTERNAL_ERROR' },
    });
  });

  it('preserves only a validated public error and marks 409 for resynchronization', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        response(409, {
          error: {
            code: 'INVALID_STATE',
            message: 'The run advanced. Refresh its public state.',
            retryable: true,
            error_id: 'public-error-1',
            schema_version: '1.0',
          },
        }),
      ),
    );
    await expect(new HttpTransport().confirmRevision('run-1', {
      proposal_id: 'proposal-1', decision: 'confirm', schema_version: '1.0',
    })).rejects.toMatchObject({
      status: 409,
      publicError: {
        code: 'INVALID_STATE',
        message: 'The run advanced. Refresh its public state.',
        retryable: true,
        error_id: 'public-error-1',
      },
    });
  });

  it.each([
    ['non-JSON response', vi.fn().mockResolvedValue({ ok: false, status: 500, text: async () => 'provider secret' })],
    ['malformed wrapper', vi.fn().mockResolvedValue(response(500, { detail: 'stack trace' }))],
    ['network rejection', vi.fn().mockRejectedValue(new Error('internal host leaked'))],
  ])('converts a %s to a generic safe public error', async (_label, implementation) => {
    vi.stubGlobal('fetch', implementation);
    const promise = new HttpTransport().getRun('run-1');
    await expect(promise).rejects.toMatchObject({ publicError: { code: 'PROVIDER_UNAVAILABLE', retryable: true } });
    await expect(promise).rejects.not.toThrow(/provider secret|stack trace|internal host leaked/);
  });

  it('honors caller cancellation and the bounded request timeout', async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init?: RequestInit) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
        }),
      ),
    );
    const controller = new AbortController();
    const cancelled = new HttpTransport().getRun('run-1', controller.signal);
    controller.abort();
    await expect(cancelled).rejects.toMatchObject({ name: 'AbortError' });

    const timedOut = new HttpTransport('', 25).getRun('run-2');
    const assertion = expect(timedOut).rejects.toMatchObject({ publicError: { code: 'PROVIDER_UNAVAILABLE', retryable: true } });
    await vi.advanceTimersByTimeAsync(25);
    await assertion;
  });
});
