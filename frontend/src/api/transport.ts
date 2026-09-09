import type {
  ConfirmContractRequest,
  ConfirmRevisionRequest,
  CreateRunRequest,
  CreateRunResponse,
  PublicError,
  RunView,
  SelectFindingsRequest,
} from './types';

export type AgentSimulationRequest = {
  title: string;
  text: string;
  seedText: string;
  populationSize: number;
  groups: string;
  /** The public PolicyFuzz run whose confirmed contract gates this launch. */
  confirmedRunId?: string;
  /** Hashes of the server-held Step 1 artifacts used as the launch gate. */
  confirmedArtifacts?: {
    policyIrSha256: string;
    contractSha256: string;
    suiteSha256: string;
  };
};

export type AgentSimulationResult = {
  run_id: string;
  status: string;
  compatibility_mode?: string;
  policy_title?: string;
  policy_source_text?: string;
  message?: string;
  error?: string | null;
  document?: { filename?: string; text?: string } | null;
  ir?: { title?: string; source?: { text?: string }; rules?: Array<{ id?: string; statement?: string }> } | null;
  effectiveness?: {
    score?: number;
    swarm_used?: boolean;
    interaction_verified?: boolean;
    justification?: string;
    metrics?: Record<string, unknown>;
    highlights?: Array<{ agent?: string; platform?: string; kind?: string; text?: string; why_significant?: string }>;
  } | null;
  evaluation?: { findings?: Array<{ scenario_id?: string; verdict?: string; summary?: string; rule_ids?: string[]; [key: string]: unknown }> } | null;
  extra?: { swarm?: { interaction_verified?: boolean; duplicate_messages_rejected?: number; error?: string; posts?: Array<{ agent?: string; user_name?: string; text?: string; content?: string; [key: string]: unknown }>; comments?: Array<{ agent?: string; user_name?: string; text?: string; content?: string; [key: string]: unknown }>; actions?: Array<{ agent?: string; agent_name?: string; text?: string; content?: string; [key: string]: unknown }> } };
};

export interface PolicyFuzzTransport {
  readonly dataSourceLabel?: string;
  /** Explicitly enabled only by a transport that can run independent simulations. */
  readonly supportsAgentSimulation?: boolean;
  createRun(request: CreateRunRequest, signal?: AbortSignal): Promise<CreateRunResponse>;
  getRun(runId: string, signal?: AbortSignal): Promise<RunView>;
  confirmContract(runId: string, request: ConfirmContractRequest, signal?: AbortSignal): Promise<RunView>;
  selectFindings(runId: string, request: SelectFindingsRequest, signal?: AbortSignal): Promise<RunView>;
  confirmRevision(runId: string, request: ConfirmRevisionRequest, signal?: AbortSignal): Promise<RunView>;
  deleteRun(runId: string, signal?: AbortSignal): Promise<void>;
  startAgentSimulation?(request: AgentSimulationRequest, signal?: AbortSignal): Promise<AgentSimulationResult>;
  startCustomAgentSimulation?(request: AgentSimulationRequest, signal?: AbortSignal): Promise<AgentSimulationResult>;
  loadAgentSimulation?(engineRunId: string, signal?: AbortSignal): Promise<AgentSimulationResult>;
}

export class PublicTransportError extends Error {
  readonly publicError: PublicError;
  readonly status?: number;

  constructor(publicError: PublicError, status?: number) {
    super(publicError.message);
    this.name = 'PublicTransportError';
    this.publicError = publicError;
    this.status = status;
  }
}

export function safePublicError(
  code: PublicError['code'],
  message: string,
  retryable = false,
): PublicTransportError {
  return new PublicTransportError({ code, message, retryable, error_id: null, schema_version: '1.0' });
}
