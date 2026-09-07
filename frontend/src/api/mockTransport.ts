import { PublicTransportError, safePublicError, type AgentSimulationRequest, AgentSimulationResult, type PolicyFuzzTransport } from './transport';
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
  validateConfirmContractRequest,
  validateConfirmRevisionRequest,
  validateCreateRunRequest,
  validateRunView,
  validateSelectFindingsRequest,
} from './validateRunView';
import {
  makeAwaitingContractView,
  makeAwaitingFindingsView,
  makeAwaitingRevisionView,
  makeCompletedView,
  makeRunView,
} from '../fixtures/cachedRunView';

type AlternateTerminalStage = Exclude<
  NonNullable<RunView['terminal_status']>,
  'complete' | 'contract_rejected' | 'revision_rejected'
>;

export type MockTransportOptions = {
  terminalStage?: AlternateTerminalStage;
};

type StoredRun = {
  current: RunView;
  next?: RunView;
};

function clone<T>(value: T): T {
  return structuredClone(value);
}

function abortIfNeeded(signal?: AbortSignal): void {
  signal?.throwIfAborted();
}

const notFound = () =>
  new PublicTransportError(
    { code: 'RUN_NOT_FOUND', message: 'The run was not found.', retryable: false, error_id: null, schema_version: '1.0' },
    404,
  );
const invalidState = (message = 'The command does not match the current public run state.') =>
  new PublicTransportError(
    { code: 'INVALID_STATE', message, retryable: false, error_id: null, schema_version: '1.0' },
    409,
  );

export class MockTransport implements PolicyFuzzTransport {
  readonly dataSourceLabel = 'Cached synthetic fixture · authored display data';
  private readonly runs = new Map<string, StoredRun>();
  private readonly terminalStage?: AlternateTerminalStage;
  private nextId = 1;

  constructor(options: MockTransportOptions = {}) {
    this.terminalStage = options.terminalStage;
  }

  async startAgentSimulation(request: AgentSimulationRequest, signal?: AbortSignal): Promise<AgentSimulationResult> {
    abortIfNeeded(signal);
    if (!request.confirmedRunId) throw safePublicError('INVALID_STATE', 'Confirm the Step 1 policy contract before starting MiroFish.');
    return { run_id: 'mock-agent-run-1', status: 'completed', message: 'Mock agent simulation complete.', effectiveness: { score: 0, swarm_used: false } };
  }

  async createRun(request: CreateRunRequest, signal?: AbortSignal): Promise<CreateRunResponse> {
    abortIfNeeded(signal);
    this.validateCommand(validateCreateRunRequest, request);
    if (request.source_type === 'pasted_text') {
      if (!request.non_confidential_confirmed || !request.text) {
        throw safePublicError('INVALID_INPUT', 'Pasted text must be non-confidential and non-empty.');
      }
    } else if (!request.sample_id) {
      throw safePublicError('INVALID_INPUT', 'A bundled sample identifier is required.');
    }
    const runId = `synthetic-mock-run-${this.nextId++}`;
    this.runs.set(runId, {
      current: this.withRunId(makeRunView('queued'), runId),
      next: this.withRunId(makeAwaitingContractView(), runId),
    });
    abortIfNeeded(signal);
    return { run_id: runId, schema_version: '1.0' };
  }

  async getRun(runId: string, signal?: AbortSignal): Promise<RunView> {
    abortIfNeeded(signal);
    const stored = this.requireRun(runId);
    if (stored.next) {
      stored.current = stored.next;
      stored.next = undefined;
    }
    const result = clone(stored.current);
    abortIfNeeded(signal);
    return result;
  }

  async confirmContract(
    runId: string,
    request: ConfirmContractRequest,
    signal?: AbortSignal,
  ): Promise<RunView> {
    abortIfNeeded(signal);
    this.validateCommand(validateConfirmContractRequest, request);
    const stored = this.requireStage(runId, 'awaiting_contract');
    const pending = stored.current.pending_confirmation;
    if (pending?.kind !== 'contract') throw invalidState();
    if (request.decision === 'reject') {
      return this.setTerminal(stored, runId, 'contract_rejected', signal);
    }
    if (
      request.baseline_policy_id !== pending.baseline_policy_id ||
      request.baseline_policy_sha256 !== pending.baseline_policy_sha256 ||
      [...request.required_dimensions].sort().join('\0') !== [...pending.required_dimensions].sort().join('\0')
    ) {
      throw invalidState('The contract confirmation does not match the server-held synthetic baseline.');
    }
    const active = this.withRunId(makeRunView('generating_initial_tests'), runId);
    stored.current = active;
    stored.next = this.withRunId(makeAwaitingFindingsView(), runId);
    abortIfNeeded(signal);
    return clone(active);
  }

  async selectFindings(
    runId: string,
    request: SelectFindingsRequest,
    signal?: AbortSignal,
  ): Promise<RunView> {
    abortIfNeeded(signal);
    this.validateCommand(validateSelectFindingsRequest, request);
    const stored = this.requireStage(runId, 'awaiting_finding_review');
    const pending = stored.current.pending_confirmation;
    if (pending?.kind !== 'findings') throw invalidState();
    const expected = [...pending.finding_ids].sort();
    const actual = request.decisions.map((decision) => decision.finding_id).sort();
    if (actual.length !== new Set(actual).size || actual.join('\0') !== expected.join('\0')) {
      throw invalidState('Every reviewable synthetic finding requires one decision.');
    }
    for (const decision of request.decisions) {
      const finding = stored.current.findings?.find((item) => item.finding_id === decision.finding_id);
      if (
        decision.decision === 'accept' &&
        (finding?.finding_type === 'structural_gap' || finding?.finding_type === 'conflict') &&
        !finding.severity &&
        !decision.reviewer_severity
      ) {
        throw safePublicError('INVALID_INPUT', 'Accepted structural findings require reviewer severity.');
      }
    }
    const decisions = new Map(request.decisions.map((decision) => [decision.finding_id, decision]));
    const reviewedFindings = stored.current.findings.map((finding) => {
      const decision = decisions.get(finding.finding_id);
      if (!decision) return clone(finding);
      return {
        ...clone(finding),
        review_status: decision.decision === 'accept' ? 'accepted' as const : 'rejected' as const,
        severity: decision.decision === 'accept' ? decision.reviewer_severity ?? finding.severity : finding.severity,
      };
    });
    const acceptedIds = request.decisions
      .filter((decision) => decision.decision === 'accept')
      .map((decision) => decision.finding_id)
      .sort();
    if (acceptedIds.join('\0') !== 'synthetic-finding-cap') {
      stored.current = this.reviewedTransition(stored.current, runId, reviewedFindings, 'completed_no_revision');
      stored.next = undefined;
      abortIfNeeded(signal);
      return clone(stored.current);
    }
    const active = this.reviewedTransition(stored.current, runId, reviewedFindings, 'drafting_revision');
    stored.current = active;
    const revision = this.withRunId(makeAwaitingRevisionView(), runId);
    revision.findings = clone(reviewedFindings);
    stored.next = validateRunView(revision);
    abortIfNeeded(signal);
    return clone(active);
  }

  async confirmRevision(
    runId: string,
    request: ConfirmRevisionRequest,
    signal?: AbortSignal,
  ): Promise<RunView> {
    abortIfNeeded(signal);
    this.validateCommand(validateConfirmRevisionRequest, request);
    const stored = this.requireStage(runId, 'awaiting_revision_confirmation');
    const pending = stored.current.pending_confirmation;
    if (pending?.kind !== 'revision' || request.proposal_id !== pending.proposal_id) {
      throw invalidState('The revision confirmation does not match the server-held synthetic proposal.');
    }
    if (request.decision === 'reject') {
      return this.setTerminal(stored, runId, 'revision_rejected', signal);
    }
    const reviewedFindings = clone(stored.current.findings);
    const active = this.withRunId(makeRunView('applying_revision'), runId);
    active.findings = clone(reviewedFindings);
    stored.current = active;
    const terminal = this.terminalStage
      ? makeRunView(this.terminalStage)
      : this.completedFromReview(reviewedFindings);
    stored.next = this.withRunId(
      terminal,
      runId,
    );
    abortIfNeeded(signal);
    return clone(active);
  }

  async deleteRun(runId: string, signal?: AbortSignal): Promise<void> {
    abortIfNeeded(signal);
    if (!this.runs.delete(runId)) throw notFound();
    abortIfNeeded(signal);
  }

  private requireRun(runId: string): StoredRun {
    const stored = this.runs.get(runId);
    if (!stored) throw notFound();
    return stored;
  }

  private requireStage(runId: string, stage: RunView['stage']): StoredRun {
    const stored = this.requireRun(runId);
    if (stored.current.stage !== stage) throw invalidState();
    return stored;
  }

  private withRunId(view: RunView, runId: string): RunView {
    const result = clone(view);
    result.run_id = runId;
    return validateRunView(result);
  }

  private setTerminal(
    stored: StoredRun,
    runId: string,
    stage: 'contract_rejected' | 'revision_rejected',
    signal?: AbortSignal,
  ): RunView {
    stored.current = this.withRunId(makeRunView(stage), runId);
    stored.next = undefined;
    abortIfNeeded(signal);
    return clone(stored.current);
  }

  private reviewedTransition(
    current: RunView,
    runId: string,
    findings: RunView['findings'],
    stage: 'drafting_revision' | 'completed_no_revision',
  ): RunView {
    const result = clone(current);
    result.run_id = runId;
    result.stage = stage;
    result.findings = clone(findings);
    result.pending_confirmation = null;
    result.allowed_actions = ['delete_run'];
    result.terminal_status = stage === 'completed_no_revision' ? 'completed_no_revision' : null;
    result.events = [
      ...result.events,
      {
        schema_version: '1.0',
        timestamp: '2026-09-04T12:01:00Z',
        stage,
        action_summary: stage === 'completed_no_revision'
          ? 'Authored synthetic review ended without a supported revision.'
          : 'Authored synthetic accepted finding moved to revision drafting.',
        artifact: null,
        error_id: null,
      },
    ];
    return validateRunView(result);
  }

  private completedFromReview(findings: RunView['findings']): RunView {
    const result = makeCompletedView();
    result.findings = clone(findings);
    if (result.baseline_metrics) result.baseline_metrics.unique_finding_count = findings.length;
    if (result.comparison_metrics) {
      result.comparison_metrics.baseline.unique_finding_count = findings.length;
      result.comparison_metrics.revised.unique_finding_count = findings.length;
    }
    return validateRunView(result);
  }

  private validateCommand<T>(validator: (value: unknown) => T, value: unknown): void {
    try {
      validator(value);
    } catch (error) {
      if (error instanceof PublicResponseValidationError) {
        throw safePublicError('INVALID_INPUT', 'The command does not match the public contract.');
      }
      throw error;
    }
  }
}
