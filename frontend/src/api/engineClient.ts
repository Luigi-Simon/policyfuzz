import { apiUrl } from './config';
import type { CreateRunInput, RunRecord } from './types';

type EngineErrorKind = 'http' | 'invalid-response' | 'run-failed';

const RUN_STATUSES = new Set([
  'pending',
  'ingesting',
  'extracting',
  'compiling',
  'compiled',
  'generating_scenarios',
  'scenarios_ready',
  'evaluating',
  'rehearsing',
  'completed',
  'failed',
]);
const SCENARIO_KINDS = new Set(['normal', 'boundary', 'adversarial', 'targeted']);
const EXPECTED_OUTCOMES = new Set(['compliant', 'violation', 'exception', 'ambiguous']);
const VERDICTS = new Set(['pass', 'fail', 'ambiguous', 'error']);
const PREDICATE_OPS = new Set(['eq', 'neq', 'in', 'not_in', 'gt', 'gte', 'lt', 'lte', 'exists', 'matches', 'between']);
const MODALITIES = new Set(['must', 'must_not', 'may', 'should']);
const SEVERITIES = new Set(['critical', 'high', 'medium', 'low']);
const REVISION_ACTIONS = new Set(['clarify', 'tighten', 'carve_out', 'add_rule', 'communicate']);

export const ENGINE_REQUEST_TIMEOUT_MS = 120_000;

export class EngineApiError extends Error {
  status: number;
  body: string;
  kind: EngineErrorKind;

  constructor(status: number, body: string, kind: EngineErrorKind = 'http') {
    super(body || `Engine request failed (${status})`);
    this.name = 'EngineApiError';
    this.status = status;
    this.body = body;
    this.kind = kind;
  }
}

export class EngineRequestTimeoutError extends Error {
  constructor() {
    super('Engine request timed out');
    this.name = 'EngineRequestTimeoutError';
  }
}

type JsonObject = Record<string, unknown>;

function invalid(path: string, expectation: string): never {
  throw new EngineApiError(200, `Invalid engine response at ${path}: expected ${expectation}`, 'invalid-response');
}

function objectAt(value: unknown, path: string): JsonObject {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) invalid(path, 'an object');
  return value as JsonObject;
}

function stringAt(value: unknown, path: string): string {
  if (typeof value !== 'string') invalid(path, 'a string');
  return value;
}

function booleanAt(value: unknown, path: string): boolean {
  if (typeof value !== 'boolean') invalid(path, 'a boolean');
  return value;
}

function numberAt(value: unknown, path: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) invalid(path, 'a finite number');
  return value;
}

function integerAt(value: unknown, path: string): number {
  const number = numberAt(value, path);
  if (!Number.isInteger(number)) invalid(path, 'an integer');
  return number;
}

function arrayAt(value: unknown, path: string): unknown[] {
  if (!Array.isArray(value)) invalid(path, 'an array');
  return value;
}

function stringsAt(value: unknown, path: string): string[] {
  return arrayAt(value, path).map((item, index) => stringAt(item, `${path}[${index}]`));
}

function optionalString(value: unknown, path: string): void {
  if (value !== undefined) stringAt(value, path);
}

function optionalNullableString(value: unknown, path: string): void {
  if (value !== undefined && value !== null) stringAt(value, path);
}

function optionalObject(value: unknown, path: string): void {
  if (value !== undefined) objectAt(value, path);
}

function validateJsonValue(value: unknown, path: string): void {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return;
  if (typeof value === 'number') {
    numberAt(value, path);
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => validateJsonValue(item, `${path}[${index}]`));
    return;
  }
  if (typeof value === 'object') {
    Object.entries(value).forEach(([key, item]) => validateJsonValue(item, `${path}.${key}`));
    return;
  }
  invalid(path, 'a JSON-compatible value');
}

function validateDocument(value: unknown, path: string): void {
  const document = objectAt(value, path);
  stringAt(document.document_id, `${path}.document_id`);
  stringAt(document.filename, `${path}.filename`);
  optionalString(document.text, `${path}.text`);
  if (document.page_count !== undefined) integerAt(document.page_count, `${path}.page_count`);
}

function validatePredicate(value: unknown, path: string): void {
  const predicate = objectAt(value, path);
  stringAt(predicate.field, `${path}.field`);
  if (predicate.op !== undefined && !PREDICATE_OPS.has(stringAt(predicate.op, `${path}.op`))) {
    invalid(`${path}.op`, 'a supported predicate operator');
  }
  if (predicate.value !== undefined) validateJsonValue(predicate.value, `${path}.value`);
}

function validateRule(value: unknown, path: string): void {
  const rule = objectAt(value, path);
  stringAt(rule.id, `${path}.id`);
  stringAt(rule.title, `${path}.title`);
  stringAt(rule.statement, `${path}.statement`);
  if (rule.citations !== undefined) {
    arrayAt(rule.citations, `${path}.citations`).forEach((item, index) => {
      const citationPath = `${path}.citations[${index}]`;
      const citation = objectAt(item, citationPath);
      stringAt(citation.document_id, `${citationPath}.document_id`);
      stringAt(citation.quote, `${citationPath}.quote`);
      optionalNullableString(citation.section, `${citationPath}.section`);
      if (citation.page !== undefined && citation.page !== null) integerAt(citation.page, `${citationPath}.page`);
    });
  }
  for (const field of ['when', 'except_when'] as const) {
    if (rule[field] !== undefined) {
      arrayAt(rule[field], `${path}.${field}`).forEach((item, index) => validatePredicate(item, `${path}.${field}[${index}]`));
    }
  }
  if (rule.then !== undefined) {
    arrayAt(rule.then, `${path}.then`).forEach((item, index) => {
      const obligationPath = `${path}.then[${index}]`;
      const obligation = objectAt(item, obligationPath);
      const modality = stringAt(obligation.modality, `${obligationPath}.modality`);
      if (!MODALITIES.has(modality)) invalid(`${obligationPath}.modality`, 'a supported modality');
      stringAt(obligation.action, `${obligationPath}.action`);
      optionalString(obligation.details, `${obligationPath}.details`);
    });
  }
  if (rule.severity !== undefined && !SEVERITIES.has(stringAt(rule.severity, `${path}.severity`))) {
    invalid(`${path}.severity`, 'a supported severity');
  }
}

function validatePolicyIr(value: unknown, path: string): void {
  const ir = objectAt(value, path);
  stringAt(ir.policy_id, `${path}.policy_id`);
  stringAt(ir.title, `${path}.title`);
  integerAt(ir.revision, `${path}.revision`);
  validateDocument(ir.source, `${path}.source`);
  arrayAt(ir.rules, `${path}.rules`).forEach((item, index) => validateRule(item, `${path}.rules[${index}]`));
  stringsAt(ir.open_questions, `${path}.open_questions`);
  stringsAt(ir.conflicts, `${path}.conflicts`);
}

function validateSuite(value: unknown, path: string): void {
  const suite = objectAt(value, path);
  stringAt(suite.suite_id, `${path}.suite_id`);
  stringAt(suite.policy_id, `${path}.policy_id`);
  integerAt(suite.policy_revision, `${path}.policy_revision`);
  arrayAt(suite.scenarios, `${path}.scenarios`).forEach((item, index) => {
    const scenarioPath = `${path}.scenarios[${index}]`;
    const scenario = objectAt(item, scenarioPath);
    stringAt(scenario.scenario_id, `${scenarioPath}.scenario_id`);
    const kind = stringAt(scenario.kind, `${scenarioPath}.kind`);
    if (!SCENARIO_KINDS.has(kind)) invalid(`${scenarioPath}.kind`, 'a supported scenario kind');
    stringAt(scenario.title, `${scenarioPath}.title`);
    optionalString(scenario.narrative, `${scenarioPath}.narrative`);
    if (scenario.facts !== undefined) {
      objectAt(scenario.facts, `${scenarioPath}.facts`);
      validateJsonValue(scenario.facts, `${scenarioPath}.facts`);
    }
    if (scenario.targeted_rule_ids !== undefined) stringsAt(scenario.targeted_rule_ids, `${scenarioPath}.targeted_rule_ids`);
    if (
      scenario.expected_outcome !== undefined &&
      scenario.expected_outcome !== null &&
      !EXPECTED_OUTCOMES.has(stringAt(scenario.expected_outcome, `${scenarioPath}.expected_outcome`))
    ) {
      invalid(`${scenarioPath}.expected_outcome`, 'a supported expected outcome');
    }
  });
}

function validateEvaluation(value: unknown, path: string): void {
  const evaluation = objectAt(value, path);
  stringAt(evaluation.report_id, `${path}.report_id`);
  stringAt(evaluation.policy_id, `${path}.policy_id`);
  integerAt(evaluation.policy_revision, `${path}.policy_revision`);
  stringAt(evaluation.suite_id, `${path}.suite_id`);
  arrayAt(evaluation.findings, `${path}.findings`).forEach((item, index) => {
    const findingPath = `${path}.findings[${index}]`;
    const finding = objectAt(item, findingPath);
    stringAt(finding.finding_id, `${findingPath}.finding_id`);
    stringAt(finding.scenario_id, `${findingPath}.scenario_id`);
    const verdict = stringAt(finding.verdict, `${findingPath}.verdict`);
    if (!VERDICTS.has(verdict)) invalid(`${findingPath}.verdict`, 'a supported verdict');
    stringAt(finding.summary, `${findingPath}.summary`);
    if (finding.rule_ids !== undefined) stringsAt(finding.rule_ids, `${findingPath}.rule_ids`);
    if (finding.traces !== undefined) {
      arrayAt(finding.traces, `${findingPath}.traces`).forEach((traceValue, traceIndex) => {
        const tracePath = `${findingPath}.traces[${traceIndex}]`;
        const trace = objectAt(traceValue, tracePath);
        stringAt(trace.rule_id, `${tracePath}.rule_id`);
        booleanAt(trace.matched, `${tracePath}.matched`);
        optionalString(trace.detail, `${tracePath}.detail`);
      });
    }
  });
  optionalObject(evaluation.metrics, `${path}.metrics`);
}

function validateEffectiveness(value: unknown, path: string): void {
  const effectiveness = objectAt(value, path);
  stringAt(effectiveness.report_id, `${path}.report_id`);
  stringAt(effectiveness.policy_id, `${path}.policy_id`);
  integerAt(effectiveness.policy_revision, `${path}.policy_revision`);
  const score = integerAt(effectiveness.score, `${path}.score`);
  if (score < 0 || score > 100) invalid(`${path}.score`, 'an integer from 0 to 100');
  stringAt(effectiveness.justification, `${path}.justification`);
  if (effectiveness.swarm_used !== undefined) booleanAt(effectiveness.swarm_used, `${path}.swarm_used`);
  if (effectiveness.recommended_actions !== undefined) {
    arrayAt(effectiveness.recommended_actions, `${path}.recommended_actions`).forEach((item, index) => {
      const actionPath = `${path}.recommended_actions[${index}]`;
      const action = objectAt(item, actionPath);
      const kind = stringAt(action.action, `${actionPath}.action`);
      if (!REVISION_ACTIONS.has(kind)) invalid(`${actionPath}.action`, 'a supported revision action');
      stringAt(action.summary, `${actionPath}.summary`);
      if (action.rule_ids !== undefined) stringsAt(action.rule_ids, `${actionPath}.rule_ids`);
    });
  }
  optionalObject(effectiveness.metrics, `${path}.metrics`);
}

function validateSeed(value: unknown, path: string): void {
  const seed = objectAt(value, path);
  optionalString(seed.text, `${path}.text`);
  if (seed.population_size !== undefined && seed.population_size !== null) integerAt(seed.population_size, `${path}.population_size`);
  if (seed.groups !== undefined) stringsAt(seed.groups, `${path}.groups`);
  optionalString(seed.locale, `${path}.locale`);
  if (seed.segments !== undefined) {
    arrayAt(seed.segments, `${path}.segments`).forEach((item, index) => {
      const segmentPath = `${path}.segments[${index}]`;
      const segment = objectAt(item, segmentPath);
      stringAt(segment.id, `${segmentPath}.id`);
      optionalString(segment.label, `${segmentPath}.label`);
      if (segment.weight !== undefined) numberAt(segment.weight, `${segmentPath}.weight`);
      optionalObject(segment.attributes, `${segmentPath}.attributes`);
    });
  }
}

function validateRunRecord(value: unknown): RunRecord {
  const run = objectAt(value, '$');
  stringAt(run.run_id, '$.run_id');
  const status = stringAt(run.status, '$.status');
  if (!RUN_STATUSES.has(status)) invalid('$.status', 'a supported run status');
  optionalString(run.message, '$.message');
  optionalNullableString(run.error, '$.error');
  if (run.seed !== undefined) validateSeed(run.seed, '$.seed');
  if (run.document !== undefined && run.document !== null) validateDocument(run.document, '$.document');
  if (run.ir !== undefined && run.ir !== null) validatePolicyIr(run.ir, '$.ir');
  if (run.suite !== undefined && run.suite !== null) validateSuite(run.suite, '$.suite');
  if (run.evaluation !== undefined && run.evaluation !== null) validateEvaluation(run.evaluation, '$.evaluation');
  if (run.effectiveness !== undefined && run.effectiveness !== null) validateEffectiveness(run.effectiveness, '$.effectiveness');
  optionalString(run.created_at, '$.created_at');
  optionalString(run.updated_at, '$.updated_at');
  return value as RunRecord;
}

async function parseJson<T>(response: Response, validate: (value: unknown) => T): Promise<T> {
  const text = await response.text();
  if (!response.ok) {
    throw new EngineApiError(response.status, text || response.statusText);
  }
  if (!text) {
    throw new EngineApiError(response.status, 'Empty response from engine');
  }
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    throw new EngineApiError(response.status, 'Engine response was not valid JSON', 'invalid-response');
  }
  return validate(value);
}

async function fetchWithTimeout(url: string, init: RequestInit = {}, callerSignal?: AbortSignal): Promise<Response> {
  const controller = new AbortController();
  let timedOut = false;
  const cancel = () => controller.abort(callerSignal?.reason);
  if (callerSignal?.aborted) cancel();
  else callerSignal?.addEventListener('abort', cancel, { once: true });
  const timer = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, ENGINE_REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (error) {
    if (timedOut) throw new EngineRequestTimeoutError();
    throw error;
  } finally {
    window.clearTimeout(timer);
    callerSignal?.removeEventListener('abort', cancel);
  }
}

export function userFacingEngineError(error: unknown, operation: string): string {
  if (error instanceof EngineRequestTimeoutError) {
    return `${operation} timed out. Check the engine and try again.`;
  }
  if (error instanceof EngineApiError) {
    if (error.kind === 'invalid-response') return `${operation} failed because the engine returned an invalid response.`;
    if (error.kind === 'run-failed') return `${operation} could not be completed. Check the engine and try again.`;
    return `${operation} failed (HTTP ${error.status}). Check the engine and try again.`;
  }
  return `${operation} failed. Check the engine and try again.`;
}

export async function checkHealth(signal?: AbortSignal): Promise<{ status: string; service?: string }> {
  const response = await fetchWithTimeout(apiUrl('/health'), {}, signal);
  return parseJson(response, (value) => {
    const health = objectAt(value, '$');
    stringAt(health.status, '$.status');
    optionalString(health.service, '$.service');
    return value as { status: string; service?: string };
  });
}

export async function createRun(input: CreateRunInput, signal?: AbortSignal): Promise<RunRecord> {
  const form = new FormData();
  form.append('policy_text', input.policyText);
  if (input.seedText) form.append('seed_text', input.seedText);
  if (input.populationSize != null) form.append('population_size', String(input.populationSize));
  if (input.groups?.length) form.append('groups', input.groups.join(','));
  if (input.segments?.length) form.append('audience_json', JSON.stringify(input.segments));
  if (input.locale) form.append('locale', input.locale);

  const response = await fetchWithTimeout(apiUrl('/v1/runs'), {
    method: 'POST',
    body: form,
  }, signal);
  return parseJson(response, validateRunRecord);
}

export async function getRun(runId: string, signal?: AbortSignal): Promise<RunRecord> {
  const response = await fetchWithTimeout(apiUrl(`/v1/runs/${encodeURIComponent(runId)}`), {}, signal);
  return parseJson(response, validateRunRecord);
}

export async function reviseRun(runId: string, instruction: string, signal?: AbortSignal): Promise<RunRecord> {
  const response = await fetchWithTimeout(apiUrl(`/v1/runs/${encodeURIComponent(runId)}/revise`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ instruction }),
  }, signal);
  return parseJson(response, validateRunRecord);
}

export async function rehearseRun(runId: string, swarm = true, signal?: AbortSignal): Promise<RunRecord> {
  const qs = swarm ? '?swarm=true' : '';
  const response = await fetchWithTimeout(apiUrl(`/v1/runs/${encodeURIComponent(runId)}/rehearse${qs}`), {
    method: 'POST',
  }, signal);
  return parseJson(response, validateRunRecord);
}
