export const metricPolicy = {
  title: 'Synthetic SG transport claims policy',
  description: 'Each transport claim is capped at SGD 100. Each participant has a SGD 150 allowance. Approved claims do not reserve allowance. Recheck the allowance when paying. Reject duplicate claim IDs.',
  agent_seed: 'Include commuters with varied transport needs.',
  agent_count: 3,
};

export const metricReview = {
  policy_text_sha256: 'a'.repeat(64),
  review_fingerprint: 'b'.repeat(64),
  status: 'ready' as const,
  clauses: [
    { id: 'C1', text: 'Each transport claim is capped at SGD 100.' },
    { id: 'C2', text: 'Each participant has a SGD 150 paid allowance.' },
  ],
  goals: [
    { id: 'G1', text: 'A claim at the stated limit can be paid.', clause_ids: ['C1', 'C2'] },
  ],
  rules: {
    per_claim_limit_cents: 10_000,
    participant_allowance_cents: 15_000,
    approval_budget_accounting: 'paid_only' as const,
    payment_budget_recheck: true,
    duplicate_scope: 'claim_id' as const,
  },
  assumptions: ['Money values use integer SGD cents.'],
  limitations: ['Only synthetic Singapore transport reimbursement claims are supported.'],
};

const submitAction = {
  action: 'submit' as const,
  claim_id: 'CL1',
  participant_id: 'P1',
  journey_id: 'J1',
  amount_cents: 10_000,
};

const traceStep = {
  step_id: 'S1',
  action_index: 0,
  action: submitAction,
  accepted: true,
  detail: 'The claim was submitted.',
  before_state_sha256: 'c'.repeat(64),
  after_state_sha256: 'd'.repeat(64),
  participant_paid_cents_before: 0,
  participant_paid_cents_after: 0,
  participant_reserved_cents_before: 0,
  participant_reserved_cents_after: 0,
};

export const metricResult = {
  schema_version: '2.0' as const,
  run_id: 'RUN1',
  policy_version: '1' as const,
  policy_text_sha256: metricReview.policy_text_sha256,
  review_fingerprint: metricReview.review_fingerprint,
  generation_method: 'rule_templates' as const,
  status: 'completed' as const,
  review: metricReview,
  suite_sha256: 'e'.repeat(64),
  cases: [
    {
      case_id: 'CASE1',
      title: 'Claim at the per-claim limit',
      category: 'boundary' as const,
      plausibility: 'A commuter submits one claim at the published limit.',
      initial_state: { claims: [], participants: [] },
      actions: [submitAction],
      trace: [traceStep],
      assertions: [{
        requirement_id: 'G1',
        passed: true,
        expected: 'The valid claim is accepted.',
        actual: 'The claim was accepted.',
        step_refs: ['S1'],
      }],
      verdict: 'pass' as const,
      unscored_reason: null,
      minimal_actions: null,
    },
    {
      case_id: 'CASE2',
      title: 'Second payment exceeds the allowance',
      category: 'cascading' as const,
      plausibility: 'A commuter submits another ordinary claim after using most of the allowance.',
      initial_state: {
        claims: [
          { claim_id: 'OLD1', participant_id: 'P1', journey_id: 'J0', amount_cents: 10_000, status: 'paid' as const },
          { claim_id: 'OLD2', participant_id: 'P2', journey_id: 'J2', amount_cents: 5_000, status: 'approved' as const },
        ],
        participants: [
          { participant_id: 'P1', paid_cents: 10_000, reserved_cents: 0 },
          { participant_id: 'P2', paid_cents: 0, reserved_cents: 5_000 },
        ],
      },
      actions: [submitAction],
      trace: [traceStep],
      assertions: [{
        requirement_id: 'G1',
        passed: false,
        expected: 'The allowance is enforced at payment.',
        actual: 'The payment was accepted above the allowance.',
        step_refs: ['S1'],
      }],
      verdict: 'fail' as const,
      unscored_reason: null,
      minimal_actions: [submitAction],
    },
  ],
  passed: 1,
  failed: 1,
  unscored: 0,
  pass_rate: 0.5,
  limitations: ['The suite uses deterministic rule-derived templates for one bounded domain.'],
};

export const clarificationReview = {
  ...metricReview,
  status: 'needs_clarification' as const,
  clauses: [{ id: 'C1', text: 'The policy contains unsupported prose.' }],
  goals: [],
  rules: null,
  assumptions: [],
  limitations: ['Clarify the claim limit and participant allowance before running tests.'],
};

export const unscoredResult = {
  ...metricResult,
  cases: [{
    case_id: 'CASE3',
    title: 'Unsupported fare adjustment',
    category: 'adversarial' as const,
    plausibility: 'A fare adjustment can occur in a transport reimbursement workflow.',
    initial_state: { claims: [], participants: [] },
    actions: [{ action: 'adjust_fare', parameters: ['manual review'] }],
    trace: [{
      ...traceStep,
      action: { action: 'adjust_fare', parameters: ['manual review'] },
      accepted: false,
      detail: 'The action is outside the supported executor.',
    }],
    assertions: [],
    verdict: 'unscored' as const,
    unscored_reason: 'The executor does not support fare adjustments.',
    minimal_actions: null,
  }],
  passed: 0,
  failed: 0,
  unscored: 1,
  pass_rate: null,
};
