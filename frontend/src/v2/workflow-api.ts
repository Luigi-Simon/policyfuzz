import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import schema from '../../../contracts/v2-app/workflow-result.schema.json';
import type { components } from './api.generated';
import { requiredWireFields, validateResult } from './api';

export type WorkflowRequest = components['schemas']['WorkflowRequest'];
export type WorkflowResult = components['schemas']['WorkflowResult'];
export type Capabilities = components['schemas']['WorkflowCapabilities'];
export type Policy = components['schemas']['RunPolicyInput'];
export type Citation = components['schemas']['Citation'];
export type CreateWorkflow = (request: WorkflowRequest, signal: AbortSignal) => Promise<WorkflowResult>;
export class WorkflowError extends Error {}

const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
const check = ajv.compile<WorkflowResult>(requiredWireFields(schema) as object);

export function validateWorkflow(value: unknown, mode: WorkflowRequest['mode'] = 'fixture'): WorkflowResult {
  const invalid = (): never => { throw new WorkflowError('The workflow response could not be verified.'); };
  if (!check(value)) return invalid();
  if (value.execution_mode !== mode) return invalid();
  const { metric, sandbox, judge } = value;
  for (const stage of [metric, sandbox, judge]) {
    if (stage && (stage.run_id !== value.run_id || stage.policy_version !== value.policy_version || stage.policy_text_sha256 !== value.policy_text_sha256)) return invalid();
  }
  if (sandbox) {
    try { validateResult(sandbox, value.execution_mode); } catch { return invalid(); }
    if (sandbox.policy_title !== value.policy_title) return invalid();
  }
  const caseIds = new Set(metric.cases.map(c => c.case_id));
  if (caseIds.size !== metric.cases.length || metric.passed !== metric.cases.filter(c => c.verdict === 'pass').length ||
      metric.failed !== metric.cases.filter(c => c.verdict === 'fail').length || metric.unscored !== metric.cases.filter(c => c.verdict === 'unscored').length ||
      metric.pass_rate !== (metric.passed + metric.failed ? metric.passed / (metric.passed + metric.failed) : null) ||
      metric.review.policy_text_sha256 !== value.policy_text_sha256 || metric.review_fingerprint !== metric.review.review_fingerprint ||
      (metric.status === 'needs_clarification' && (metric.cases.length > 0 || metric.review.status !== 'needs_clarification')) ||
      (metric.status === 'completed' && metric.review.status !== 'ready')) return invalid();
  if (metric.generation_method !== 'policy_scenarios' && metric.status === 'partial' && (metric.review.status !== 'ready' || !metric.cases.length || !metric.limitations.length)) return invalid();
  if (metric.generation_method === 'policy_conditions') {
    if (metric.status !== 'partial' || !metric.review.rules || !('conditions' in metric.review.rules)) return invalid();
    const conditions = new Set(metric.review.rules.conditions.map(c => c.id));
    if (conditions.size !== metric.review.rules.conditions.length || metric.cases.some(c => c.actions.some(a => a.action === 'evaluate_condition' && 'condition_id' in a && !conditions.has(a.condition_id)))) return invalid();
  } else if (metric.review.rules && 'conditions' in metric.review.rules) return invalid();
  if (metric.generation_method === 'policy_scenarios' && (metric.status !== 'partial' || metric.review.status !== 'needs_clarification' || metric.review.rules !== null || metric.review.clauses.length || metric.review.goals.length || !metric.cases.length || !metric.limitations.length || metric.cases.some(c => c.verdict !== 'unscored' || c.trace.length || c.actions.some(a => a.action !== 'review_scenario')))) return invalid();
  const goals = new Set(metric.review.goals.map(g => g.id));
  for (const c of metric.cases) {
    const steps = new Set(c.trace.map(s => s.step_id));
    if (steps.size !== c.trace.length || c.assertions.some(a => !goals.has(a.requirement_id) || a.step_refs.some(id => !steps.has(id))) ||
        (c.verdict === 'pass' && (!c.assertions.length || c.assertions.some(a => !a.passed))) ||
        (c.verdict === 'fail' && !c.assertions.some(a => !a.passed)) ||
        (c.verdict === 'unscored' && (c.assertions.length || !c.unscored_reason))) return invalid();
  }
  const incomplete = metric.status !== 'completed' || !metric.cases.length || metric.unscored > 0 || !sandbox || sandbox.status !== 'completed';
  if (judge) {
    if (judge.execution_mode !== mode || (judge.status === 'partial' && !judge.limitations.length) ||
        (judge.status !== 'failed' && (judge.errors.length || !judge.next_steps.length || (incomplete && judge.status !== 'partial'))) ||
        (judge.status === 'failed' && (!judge.errors.length || judge.recommendation !== 'insufficient_evidence' || judge.pros.length || judge.cons.length || judge.key_interactions.length || judge.next_steps.length)) ||
        (judge.recommendation === 'consider_limited_pilot' && (mode === 'fixture' || incomplete || metric.failed > 0 || !metric.passed || metric.generation_method === 'authored_fixture'))) return invalid();
    const clauses = new Set([...metric.review.clauses, ...metric.review.goals].map(c => c.id));
    const messages = new Map(sandbox?.messages.map(m => [m.message_id, m]) ?? []);
    const validRef = (ref: Citation) => {
      if (ref.kind === 'metric_case') return ref.case_id === null && caseIds.has(ref.id);
      if (ref.kind === 'policy_clause') return ref.case_id === null && clauses.has(ref.id);
      if (ref.kind === 'metric_step') return metric.cases.some(c => c.case_id === ref.case_id && c.trace.some(s => s.step_id === ref.id));
      return ref.case_id === null && messages.has(ref.id) && messages.get(ref.id)?.translation_status !== 'unavailable';
    };
    if ([...judge.pros, ...judge.cons, ...judge.next_steps, ...judge.key_interactions].some(item => item.citations.some(ref => !validRef(ref)))) return invalid();
    for (const interaction of judge.key_interactions) {
      const ids = interaction.citations.filter(c => c.kind === 'sandbox_message').map(c => c.id);
      if (!ids.some(id => messages.get(id)?.reply_to_message_ids.some(parentId => ids.includes(parentId) && messages.get(parentId)?.persona_id !== messages.get(id)?.persona_id))) return invalid();
    }
  }
  const roles = new Set(value.stages.map(s => s.role));
  if (roles.size !== 4 || value.stages.length !== 4 || (value.status === 'completed' &&
      (incomplete || !judge || judge.status !== 'completed' || value.stages.some(s => s.status !== 'completed')))) return invalid();
  return value;
}

export const createWorkflow: CreateWorkflow = async (request, signal) => {
  const response = await fetch('/api/v2/workflows', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request), signal });
  if (!response.ok) throw new WorkflowError(response.status === 422 ? 'Check the policy fields and run settings.' : response.status === 503 ? 'Live services are not configured on the server.' : 'The workflow could not complete. Check the local services.');
  let data: unknown;
  try { data = await response.json(); } catch { throw new WorkflowError('The workflow response could not be verified.'); }
  const result = validateWorkflow(data, request.mode);
  const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(request.policy.description)))].map(b => b.toString(16).padStart(2, '0')).join('');
  if (hash !== result.policy_text_sha256 || result.policy_title !== request.policy.title ||
      (result.sandbox && result.sandbox.requested_stakeholder_count !== request.policy.agent_count)) throw new WorkflowError('The workflow response does not match the submitted policy.');
  return result;
};

export async function loadCapabilities(): Promise<Capabilities> {
  const response = await fetch('/api/v2/workflows/capabilities');
  if (!response.ok) throw new WorkflowError('The v2 service is unavailable.');
  const value = await response.json();
  if (typeof value.live_available !== 'boolean' || typeof value.live_detail !== 'string') throw new WorkflowError('The v2 service response is invalid.');
  return value;
}

export async function loadSample(): Promise<Policy> {
  const response = await fetch('/api/v2/workflows/sample');
  if (!response.ok) throw new WorkflowError('The synthetic example could not be loaded.');
  return response.json();
}
