import Ajv2020 from 'ajv/dist/2020';
import metricReviewSchema from '../../../contracts/v2-app/metric-review.schema.json';
import metricRunSchema from '../../../contracts/v2-app/metric-run-result.schema.json';
import openapi from '../../../contracts/v2-app/openapi.json';
import type { components } from './api.generated';

export type RunPolicyInput = components['schemas']['RunPolicyInput'];
export type MetricReview = components['schemas']['MetricReview'];
export type MetricRunResult = components['schemas']['MetricRunResult'];
export type MetricAction = components['schemas']['SubmitAction'] |
  components['schemas']['ApproveAction'] |
  components['schemas']['PayAction'] |
  components['schemas']['CancelAction'] |
  components['schemas']['UnsupportedAction'];
export type LoadMetricSample = (signal: AbortSignal) => Promise<RunPolicyInput>;
export type PrepareMetric = (policy: RunPolicyInput, signal: AbortSignal) => Promise<MetricReview>;
export type RunMetric = (policy: RunPolicyInput, review: MetricReview, signal: AbortSignal) => Promise<MetricRunResult>;

export class MetricError extends Error {
  constructor(message: string, readonly displaySafe = false) { super(message); }
}

// Pydantic serializes defaults on the wire. Require every declared property at
// runtime so optional generated fields cannot silently disappear from evidence.
function requiredWireFields(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(requiredWireFields);
  if (value === null || typeof value !== 'object') return value;
  const result = Object.fromEntries(Object.entries(value).map(([key, item]) => [key, requiredWireFields(item)]));
  if (result.properties && typeof result.properties === 'object') result.required = Object.keys(result.properties);
  return result;
}

const ajv = new Ajv2020({ strict: false, allErrors: true });
const checkPolicy = ajv.compile<RunPolicyInput>(
  requiredWireFields(openapi.components.schemas.RunPolicyInput) as object,
);
const checkReview = ajv.compile<MetricReview>(requiredWireFields(metricReviewSchema) as object);
const checkResult = ajv.compile<MetricRunResult>(requiredWireFields(metricRunSchema) as object);
const han = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u{20000}-\u{3134f}]/u;

function invalid(): never {
  throw new MetricError('The Metric response could not be verified.');
}

function duplicates(values: string[]): boolean {
  return values.length !== new Set(values).size;
}

function actionText(action: MetricAction): string[] {
  return 'parameters' in action ? action.parameters ?? [] : [];
}

function sameAction(left: MetricAction, right: MetricAction): boolean {
  if (left.action !== right.action) return false;
  if ('parameters' in left || 'parameters' in right) {
    return 'parameters' in left && 'parameters' in right && left.parameters.length === right.parameters.length &&
      left.parameters.every((value, index) => value === right.parameters[index]);
  }
  if (!('claim_id' in left) || !('claim_id' in right) || left.claim_id !== right.claim_id) return false;
  return left.action !== 'submit' || right.action === 'submit' &&
    left.participant_id === right.participant_id && left.journey_id === right.journey_id && left.amount_cents === right.amount_cents;
}

export function validateMetricPolicy(value: unknown): RunPolicyInput {
  if (!checkPolicy(value) || [value.title, value.description, value.agent_seed].some(text => han.test(text))) return invalid();
  return value;
}

export function validateMetricReview(value: unknown): MetricReview {
  if (!checkReview(value)) return invalid();
  const clauses = value.clauses ?? [];
  const goals = value.goals ?? [];
  const clauseIds = clauses.map(clause => clause.id);
  const goalIds = goals.map(goal => goal.id);
  const clauseSet = new Set(clauseIds);
  const display = [
    ...clauses.map(clause => clause.text),
    ...goals.map(goal => goal.text),
    ...(value.assumptions ?? []),
    ...(value.limitations ?? []),
  ];
  const unresolvedGoal = goals.some(goal =>
    duplicates(goal.clause_ids) || goal.clause_ids.some(id => !clauseSet.has(id)),
  );
  if (duplicates(clauseIds) || duplicates(goalIds) || unresolvedGoal || display.some(text => han.test(text)) ||
      (value.status === 'ready' && (!value.rules || clauses.length === 0 || goals.length === 0)) ||
      (value.status === 'needs_clarification' && value.rules !== null)) return invalid();
  return value;
}

export function validateMetricResult(value: unknown, acceptedReview: MetricReview): MetricRunResult {
  if (!checkResult(value)) return invalid();
  validateMetricReview(value.review);
  const cases = value.cases ?? [];
  const goals = new Set((value.review.goals ?? []).map(goal => goal.id));
  const caseIds = cases.map(item => item.case_id);
  let semanticError = value.generation_method !== 'rule_templates' || duplicates(caseIds) ||
    value.policy_text_sha256 !== value.review.policy_text_sha256 ||
    value.review_fingerprint !== value.review.review_fingerprint ||
    value.policy_text_sha256 !== acceptedReview.policy_text_sha256 ||
    value.review_fingerprint !== acceptedReview.review_fingerprint ||
    JSON.stringify(value.review) !== JSON.stringify(acceptedReview);

  for (const item of cases) {
    const actions = item.actions;
    const trace = item.trace ?? [];
    const assertions = item.assertions ?? [];
    const traceIds = trace.map(step => step.step_id);
    const traceSet = new Set(traceIds);
    const requirementIds = assertions.map(assertion => assertion.requirement_id);
    const claimIds = (item.initial_state.claims ?? []).map(claim => claim.claim_id);
    const participantIds = (item.initial_state.participants ?? []).map(participant => participant.participant_id);
    semanticError ||= duplicates(traceIds) || duplicates(requirementIds) || duplicates(claimIds) || duplicates(participantIds) ||
      trace.some(step => step.action_index >= actions.length || !sameAction(step.action, actions[step.action_index])) ||
      assertions.some(assertion => !goals.has(assertion.requirement_id) || duplicates(assertion.step_refs) ||
        assertion.step_refs.some(id => !traceSet.has(id))) ||
      actions.concat(item.minimal_actions ?? []).some(action =>
        actionText(action).some(text => han.test(text)) ||
        ('parameters' in action && ['submit', 'approve', 'pay', 'cancel'].includes(action.action))) ||
      [item.title, item.plausibility, item.unscored_reason ?? '',
        ...trace.map(step => step.detail),
        ...assertions.flatMap(assertion => [assertion.expected, assertion.actual])].some(text => han.test(text));

    if (item.verdict === 'pass') {
      semanticError ||= assertions.length === 0 || assertions.some(assertion => !assertion.passed) ||
        item.unscored_reason !== null || item.minimal_actions !== null;
    } else if (item.verdict === 'fail') {
      semanticError ||= assertions.length === 0 || assertions.every(assertion => assertion.passed) ||
        item.unscored_reason !== null;
    } else {
      semanticError ||= assertions.length > 0 || !item.unscored_reason || item.minimal_actions !== null;
    }
  }

  const passed = cases.filter(item => item.verdict === 'pass').length;
  const failed = cases.filter(item => item.verdict === 'fail').length;
  const unscored = cases.filter(item => item.verdict === 'unscored').length;
  const denominator = passed + failed;
  const expectedRate = denominator === 0 ? null : passed / denominator;
  semanticError ||= value.passed !== passed || value.failed !== failed || value.unscored !== unscored ||
    (expectedRate === null ? value.pass_rate !== null : value.pass_rate === null || Math.abs(value.pass_rate - expectedRate) > 1e-12) ||
    (value.status === 'completed' && value.review.status !== 'ready') ||
    (value.status === 'needs_clarification' && (value.review.status !== 'needs_clarification' || cases.length > 0)) ||
    (value.limitations ?? []).some(text => han.test(text));
  if (semanticError) return invalid();
  return value;
}

async function json(response: Response): Promise<unknown> {
  try { return await response.json(); }
  catch { return invalid(); }
}

export const loadMetricSample: LoadMetricSample = async signal => {
  const response = await fetch('/api/v2/metric/sample', { signal });
  if (!response.ok) throw new MetricError('The transport claims example could not be loaded. Please retry.', true);
  return validateMetricPolicy(await json(response));
};

export const prepareMetricReview: PrepareMetric = async (policy, signal) => {
  const response = await fetch('/api/v2/metric/prepare', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ policy }), signal,
  });
  if (!response.ok) {
    const message = response.status === 422
      ? 'Check the four policy fields and review the rules again.'
      : 'The Metric service could not review this policy. Please retry.';
    throw new MetricError(message, true);
  }
  return validateMetricReview(await json(response));
};

export const runMetricTests: RunMetric = async (policy, review, signal) => {
  const response = await fetch('/api/v2/metric/runs', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ policy, review_fingerprint: review.review_fingerprint }), signal,
  });
  if (!response.ok) {
    const message = response.status === 409
      ? 'Policy inputs changed. Review the policy again.'
      : response.status === 422
        ? 'Check the four policy fields and review the rules again.'
        : 'The Metric service could not complete. Please retry.';
    throw new MetricError(message, true);
  }
  return validateMetricResult(await json(response), review);
};
