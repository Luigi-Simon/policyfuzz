import fixture from '../../../contracts/fixtures/run-view.completed.json';
import { validateRunView } from '../api/validateRunView';
import type { InvariantSummary, RunView } from '../api/types';

/** Canonical authored synthetic display data; it is not recorded model output. */
export const cachedRunView = validateRunView(fixture);

export type RunStage = RunView['stage'];

const SHA = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

const invariants: InvariantSummary[] = [
  {
    schema_version: '1.0',
    invariant_id: 'synthetic-invariant-eligibility',
    description: 'Synthetic meal expenses remain eligible.',
    when: [{ field: 'expense_category', operator: 'eq', value: 'meal', schema_version: '1.0' }],
    assertion: {
      schema_version: '1.0',
      assertion_id: 'synthetic-assertion-eligibility',
      target_kind: 'effect_value',
      dimension: 'eligibility',
      operator: 'eq',
      expected_value: 'allow',
    },
    severity: 'high',
  },
  {
    schema_version: '1.0',
    invariant_id: 'synthetic-invariant-receipt',
    description: 'Synthetic meal claims require receipts.',
    when: [{ field: 'expense_category', operator: 'eq', value: 'meal', schema_version: '1.0' }],
    assertion: {
      schema_version: '1.0',
      assertion_id: 'synthetic-assertion-receipt',
      target_kind: 'effect_value',
      dimension: 'receipt_requirement',
      operator: 'eq',
      expected_value: 'required',
    },
    severity: 'medium',
  },
  {
    schema_version: '1.0',
    invariant_id: 'synthetic-invariant-cap',
    description: 'Synthetic meal claims do not exceed the stated cap.',
    when: [{ field: 'expense_category', operator: 'eq', value: 'meal', schema_version: '1.0' }],
    assertion: {
      schema_version: '1.0',
      assertion_id: 'synthetic-assertion-cap',
      target_kind: 'effect_value',
      dimension: 'claim_cap_minor',
      operator: 'lte',
      expected_value: 5000,
    },
    severity: 'critical',
  },
];

function clone<T>(value: T): T {
  return structuredClone(value);
}

function base(stage: RunStage): RunView {
  return {
    schema_version: '1.0',
    run_id: 'synthetic-mock-run',
    stage,
    mode: 'cached',
    allowed_actions: ['delete_run'],
    artifacts: [],
    findings: [],
    traces: [],
    rejections: [],
    unsupported_clauses: [],
    events: [
      {
        schema_version: '1.0',
        timestamp: '2026-09-04T12:00:00Z',
        stage,
        action_summary: 'Authored synthetic fixture state; no model or provider call.',
        artifact: null,
        error_id: null,
      },
    ],
    baseline_metrics: null,
    comparison_metrics: null,
    decision_at: null,
    error: null,
    holdout_evidence: null,
    pending_confirmation: null,
    terminal_status: null,
    coverage: {
      schema_version: '1.0',
      covered_rules: 0,
      total_rules: 0,
      covered_predicate_branches: 0,
      total_predicate_branches: 0,
      covered_invariants: 0,
      total_invariants: 0,
      scenario_count: 0,
    },
  };
}

/** Counts below three deliberately create an invalid selection fixture for negative UI tests. */
export function makeAwaitingContractView(invariantCount = 3): RunView {
  const view = base('awaiting_contract');
  view.allowed_actions = ['confirm_contract', 'reject_contract', 'delete_run'];
  view.pending_confirmation = {
    schema_version: '1.0',
    kind: 'contract',
    baseline_policy_id: 'synthetic-policy-v1',
    baseline_policy_sha256: SHA,
    document_sha256: SHA,
    rules: [
      {
        schema_version: '1.0',
        rule_id: 'synthetic-rule-meal',
        revision: 0,
        description: 'Synthetic meal claims require a receipt and have a cap.',
        when: [{ field: 'expense_category', operator: 'eq', value: 'meal', schema_version: '1.0' }],
        effects: [
          { dimension: 'eligibility', value: 'allow', schema_version: '1.0' },
          { dimension: 'receipt_requirement', value: 'required', schema_version: '1.0' },
          { dimension: 'claim_cap_minor', value: 5000, schema_version: '1.0' },
        ],
        overrides: [],
        citations: [
          {
            schema_version: '1.0',
            citation_id: 'synthetic-citation-meal',
            kind: 'text_citation',
            span: {
              schema_version: '1.0',
              page: 1,
              start: 0,
              end: 62,
              quote: 'Synthetic sample: meal claims require receipts and are capped.',
              quote_sha256: SHA,
              section: 'Synthetic section 1',
            },
          },
        ],
        confidence_percent: 92,
      },
    ],
    invariants: clone(invariants.slice(0, invariantCount)),
    required_dimensions: ['eligibility', 'receipt_requirement', 'claim_cap_minor'],
  };
  return view;
}

export function makeAwaitingFindingsView(): RunView {
  const view = base('awaiting_finding_review');
  view.allowed_actions = ['select_findings', 'delete_run'];
  view.baseline_metrics = clone(cachedRunView.baseline_metrics);
  view.coverage = clone(cachedRunView.coverage);
  view.traces = clone(cachedRunView.traces.filter((trace) => trace.phase === 'baseline'));
  view.rejections = clone(cachedRunView.rejections);
  view.unsupported_clauses = clone(cachedRunView.unsupported_clauses);
  view.findings = [
    {
      schema_version: '1.0',
      finding_id: 'synthetic-finding-gap',
      finding_type: 'structural_gap',
      dimension: 'approval_requirement',
      summary: 'Synthetic example: approval behavior is unspecified.',
      review_status: 'pending',
      witness_count: 2,
      severity: null,
    },
    {
      schema_version: '1.0',
      finding_id: 'synthetic-finding-cap',
      finding_type: 'intent_breach',
      dimension: 'claim_cap_minor',
      summary: 'Synthetic example: a cap assertion did not hold.',
      review_status: 'pending',
      witness_count: 1,
      severity: 'high',
    },
  ];
  view.pending_confirmation = {
    schema_version: '1.0',
    kind: 'findings',
    finding_ids: view.findings.map((finding) => finding.finding_id),
  };
  return view;
}

export function makeAwaitingRevisionView(): RunView {
  const view = makeAwaitingFindingsView();
  view.stage = 'awaiting_revision_confirmation';
  view.allowed_actions = ['confirm_revision', 'reject_revision', 'delete_run'];
  view.findings = view.findings.map((finding) => ({
    ...finding,
    review_status: finding.finding_id === 'synthetic-finding-cap' ? 'accepted' : 'rejected',
  }));
  view.pending_confirmation = {
    schema_version: '1.0',
    kind: 'revision',
    proposal_id: 'synthetic-proposal-1',
    operations: [
      {
        schema_version: '1.0',
        operation: {
          schema_version: '1.0',
          kind: 'add_override',
          rule_id: 'synthetic-rule-exception',
          dimension: 'claim_cap_minor',
          target_rule_id: 'synthetic-rule-meal',
          finding_ids: ['synthetic-finding-cap'],
        },
        before: {
          schema_version: '1.0',
          rule_id: 'synthetic-rule-exception',
          revision: 0,
          description: 'Synthetic executive exception before the proposed override link.',
          when: [
            { field: 'employee_role', operator: 'eq', value: 'executive', schema_version: '1.0' },
          ],
          effects: [
            { dimension: 'claim_cap_minor', value: 7500, schema_version: '1.0' },
          ],
          overrides: [],
          citations: [
            {
              schema_version: '1.0',
              citation_id: 'synthetic-citation-exception',
              kind: 'text_citation',
              span: {
                schema_version: '1.0',
                page: 1,
                start: 63,
                end: 126,
                quote: 'Synthetic sample: executive meal exceptions allow a higher cap.',
                quote_sha256: SHA,
                section: 'Synthetic section 2',
              },
            },
          ],
          confidence_percent: 88,
        },
      },
    ],
    draft_policy_wording: 'Synthetic draft wording for review only; it has not been tested.',
  };
  view.events = [
    {
      schema_version: '1.0',
      timestamp: '2026-09-04T12:02:00Z',
      stage: 'awaiting_revision_confirmation',
      action_summary: 'Authored synthetic revision suggestion awaiting owner confirmation.',
      artifact: null,
      error_id: null,
    },
  ];
  return view;
}

export function makeCompletedView(options: { patchAccepted?: boolean } = {}): RunView {
  const view = clone(cachedRunView);
  if (options.patchAccepted === true && view.comparison_metrics) {
    view.comparison_metrics.patch_accepted = true;
    view.comparison_metrics.protected_regressions = 0;
    view.comparison_metrics.new_failures_outside_targets = 0;
    const acceptance = view.comparison_metrics.acceptance;
    acceptance.patch_accepted = true;
    acceptance.zero_protected_regressions = true;
    acceptance.zero_new_failures_outside_targets = true;
    if (acceptance.counts) {
      acceptance.counts.protected_regressions = 0;
      acceptance.counts.new_failures_outside_targets = 0;
    }
  }
  return view;
}

export function makeRunView(stage: RunStage): RunView {
  if (stage === 'awaiting_contract') return makeAwaitingContractView();
  if (stage === 'awaiting_finding_review') return makeAwaitingFindingsView();
  if (stage === 'awaiting_revision_confirmation') return makeAwaitingRevisionView();
  if (stage === 'complete') return makeCompletedView();
  const view = base(stage);
  const terminal = [
    'completed_no_findings',
    'completed_no_revision',
    'contract_rejected',
    'revision_rejected',
    'coverage_limit_exceeded',
    'failed',
  ] as const;
  if (terminal.includes(stage as (typeof terminal)[number])) {
    view.terminal_status = stage as (typeof terminal)[number];
  }
  if (stage === 'failed') {
    view.error = {
      schema_version: '1.0',
      code: 'INTERNAL_ERROR',
      message: 'The synthetic run could not continue.',
      retryable: false,
      error_id: 'synthetic-error-1',
    };
  }
  return view;
}
