import Ajv2020, { type ErrorObject, type ValidateFunction } from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import runViewSchema from '../../../contracts/jsonschema/RunView.schema.json';
import createRunRequestSchema from '../../../contracts/jsonschema/CreateRunRequest.schema.json';
import createRunResponseSchema from '../../../contracts/jsonschema/CreateRunResponse.schema.json';
import confirmContractRequestSchema from '../../../contracts/jsonschema/ConfirmContractRequest.schema.json';
import selectFindingsRequestSchema from '../../../contracts/jsonschema/SelectFindingsRequest.schema.json';
import confirmRevisionRequestSchema from '../../../contracts/jsonschema/ConfirmRevisionRequest.schema.json';
import deleteRunResponseSchema from '../../../contracts/jsonschema/DeleteRunResponse.schema.json';
import publicErrorSchema from '../../../contracts/jsonschema/PublicError.schema.json';
import type {
  ConfirmContractRequest,
  ConfirmRevisionRequest,
  CreateRunRequest,
  CreateRunResponse,
  DeleteRunResponse,
  PublicError,
  RunView,
  SelectFindingsRequest,
} from './types';

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);

type JsonSchema = Record<string, unknown>;

/**
 * openapi-typescript exposes properties carrying server defaults as required.
 * Standalone Pydantic schemas omit those names from `required`, so harden an
 * in-memory copy for the wire boundary without defaulting or mutating input.
 */
function requireSerializedDefaults<T>(value: T): T {
  if (Array.isArray(value)) return value.map(requireSerializedDefaults) as T;
  if (typeof value !== 'object' || value === null) return value;
  const schema = Object.fromEntries(
    Object.entries(value).map(([key, item]) => [key, requireSerializedDefaults(item)]),
  ) as JsonSchema;
  const properties = schema.properties;
  if (typeof properties === 'object' && properties !== null && !Array.isArray(properties)) {
    const required = new Set(Array.isArray(schema.required) ? schema.required.filter((item): item is string => typeof item === 'string') : []);
    for (const [name, property] of Object.entries(properties)) {
      if (typeof property === 'object' && property !== null && Object.hasOwn(property, 'default')) required.add(name);
    }
    if (required.size) schema.required = [...required];
  }
  return schema as T;
}

const validator: ValidateFunction<RunView> = ajv.compile(requireSerializedDefaults(runViewSchema));

function compile<T>(schema: object): ValidateFunction<T> {
  return ajv.compile<T>(requireSerializedDefaults(schema));
}

const validators = {
  createRunRequest: compile<CreateRunRequest>(createRunRequestSchema),
  createRunResponse: compile<CreateRunResponse>(createRunResponseSchema),
  confirmContractRequest: compile<ConfirmContractRequest>(confirmContractRequestSchema),
  selectFindingsRequest: compile<SelectFindingsRequest>(selectFindingsRequestSchema),
  confirmRevisionRequest: compile<ConfirmRevisionRequest>(confirmRevisionRequestSchema),
  deleteRunResponse: compile<DeleteRunResponse>(deleteRunResponseSchema),
  publicError: compile<PublicError>(publicErrorSchema),
};

export class PublicResponseValidationError extends Error {
  readonly issues: readonly ErrorObject[];

  constructor(kind: string, issues: readonly ErrorObject[] = []) {
    super(`Invalid public ${kind} response.`);
    this.name = 'PublicResponseValidationError';
    this.issues = issues;
  }
}

export function validateRunView(value: unknown): RunView {
  if (!validator(value)) {
    throw new PublicResponseValidationError('run', validator.errors ?? []);
  }
  validateRunSemantics(value);
  return value;
}

function semanticError(kind: string): never {
  throw new PublicResponseValidationError(kind);
}

function validateRunSemantics(run: RunView): void {
  const comparison = run.comparison_metrics;
  if (comparison) {
    const acceptance = comparison.acceptance;
    const counts = acceptance.counts ?? {
      target_findings: 0,
      fixed_target_findings: 0,
      new_failures_outside_targets: 0,
      protected_regressions: 0,
      baseline_gap_conflict_inconclusive_or_error: 0,
      revised_gap_conflict_inconclusive_or_error: 0,
      unrelated_rule_changes: 0,
      holdout_regressions: 0,
      schema_version: '1.0',
    };
    const allSeven = [
      acceptance.suite_hash_matches,
      acceptance.all_target_findings_fixed,
      acceptance.zero_new_failures_outside_targets,
      acceptance.zero_protected_regressions,
      acceptance.no_increase_in_gap_conflict_inconclusive_or_error,
      acceptance.unrelated_rules_unchanged,
      acceptance.holdout_not_worse,
    ].every(Boolean);
    if (
      acceptance.patch_accepted !== allSeven ||
      comparison.patch_accepted !== acceptance.patch_accepted ||
      comparison.protected_regressions !== counts.protected_regressions ||
      comparison.new_failures_outside_targets !== counts.new_failures_outside_targets
    ) {
      semanticError('run comparison');
    }
  }

  const pending = run.pending_confirmation;
  if (pending?.kind === 'revision') {
    for (const summary of pending.operations) {
      const operation = summary.operation;
      if (operation.kind === 'add_rule') {
        if (summary.before !== null) semanticError('run revision');
      } else if (summary.before?.rule_id !== operation.rule_id) {
        semanticError('run revision');
      } else if (operation.kind === 'replace_rule' && summary.before.revision !== operation.expected_revision) {
        semanticError('run revision');
      } else if (operation.kind === 'add_override' && operation.rule_id === operation.target_rule_id) {
        semanticError('run revision');
      }
    }
  }
}

function validate<T>(kind: string, fn: ValidateFunction<T>, value: unknown): T {
  if (!fn(value)) throw new PublicResponseValidationError(kind, fn.errors ?? []);
  return value;
}

export const validateCreateRunRequest = (value: unknown): CreateRunRequest => {
  const request = validate('create-run request', validators.createRunRequest, value);
  if (request.source_type === 'pasted_text') {
    if (!request.text?.trim() || request.sample_id !== null || !request.non_confidential_confirmed) {
      semanticError('create-run request');
    }
  } else if (request.sample_id === null || request.text !== null) {
    semanticError('create-run request');
  }
  return request;
};
export const validateCreateRunResponse = (value: unknown): CreateRunResponse =>
  validate('create-run', validators.createRunResponse, value);
export const validateConfirmContractRequest = (value: unknown): ConfirmContractRequest => {
  const request = validate('confirm-contract request', validators.confirmContractRequest, value);
  if (request.decision === 'confirm') {
    if (
      request.baseline_policy_id === null ||
      request.baseline_policy_sha256 === null ||
      request.invariants.length < 3 ||
      request.invariants.length > 5 ||
      request.required_dimensions.length === 0 ||
      new Set(request.invariants.map((item) => item.invariant_id)).size !== request.invariants.length ||
      new Set(request.invariants.map((item) => item.assertion.assertion_id)).size !== request.invariants.length
    ) {
      semanticError('confirm-contract request');
    }
  } else if (
    request.baseline_policy_id !== null ||
    request.baseline_policy_sha256 !== null ||
    request.invariants.length > 0 ||
    request.required_dimensions.length > 0
  ) {
    semanticError('confirm-contract request');
  }
  return request;
};
export const validateSelectFindingsRequest = (value: unknown): SelectFindingsRequest => {
  const request = validate('select-findings request', validators.selectFindingsRequest, value);
  if (new Set(request.decisions.map((item) => item.finding_id)).size !== request.decisions.length) {
    semanticError('select-findings request');
  }
  return request;
};
export const validateConfirmRevisionRequest = (value: unknown): ConfirmRevisionRequest =>
  validate('confirm-revision request', validators.confirmRevisionRequest, value);
export const validateDeleteRunResponse = (value: unknown): DeleteRunResponse =>
  validate('delete-run', validators.deleteRunResponse, value);
export const validatePublicError = (value: unknown): PublicError =>
  validate('error', validators.publicError, value);
