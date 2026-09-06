import type {
  ConfirmContractRequest,
  ConfirmRevisionRequest,
  CreateRunRequest,
  CreateRunResponse,
  PublicError,
  RunView,
  SelectFindingsRequest,
} from './types';

export interface PolicyFuzzTransport {
  readonly dataSourceLabel?: string;
  createRun(request: CreateRunRequest, signal?: AbortSignal): Promise<CreateRunResponse>;
  getRun(runId: string, signal?: AbortSignal): Promise<RunView>;
  confirmContract(runId: string, request: ConfirmContractRequest, signal?: AbortSignal): Promise<RunView>;
  selectFindings(runId: string, request: SelectFindingsRequest, signal?: AbortSignal): Promise<RunView>;
  confirmRevision(runId: string, request: ConfirmRevisionRequest, signal?: AbortSignal): Promise<RunView>;
  deleteRun(runId: string, signal?: AbortSignal): Promise<void>;
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
