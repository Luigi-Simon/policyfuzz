import type { RunView } from '../api/types';

export type ViewStep = 'input' | 'evidence' | 'findings' | 'comparison';
export type RunSnapshots = Partial<Record<ViewStep, RunView>>;

const stages: Record<Exclude<RunView['stage'], 'failed'>, ViewStep> = {
  queued: 'input', ingesting: 'input', extracting: 'input', awaiting_contract: 'input', contract_rejected: 'input',
  generating_initial_tests: 'evidence', provisional_execution: 'evidence', targeting_coverage: 'evidence',
  freezing_suite: 'evidence', baseline_execution: 'evidence', analyzing: 'evidence',
  completed_no_findings: 'evidence', coverage_limit_exceeded: 'evidence',
  awaiting_finding_review: 'findings', drafting_revision: 'findings', awaiting_revision_confirmation: 'findings',
  completed_no_revision: 'findings', revision_rejected: 'findings',
  applying_revision: 'comparison', retesting: 'comparison', complete: 'comparison',
};
const pollingStages = new Set<RunView['stage']>([
  'queued', 'ingesting', 'extracting', 'generating_initial_tests', 'provisional_execution',
  'targeting_coverage', 'freezing_suite', 'baseline_execution', 'analyzing', 'drafting_revision',
  'applying_revision', 'retesting',
]);
export function isPollingStage(stage: RunView['stage']): boolean { return pollingStages.has(stage); }

export function stageView(run: RunView): ViewStep {
  if (run.stage !== 'failed') return stages[run.stage];
  const lastEvent = [...(run.events ?? [])].reverse().find(event => event.stage !== 'failed');
  if (lastEvent) return stages[lastEvent.stage as Exclude<RunView['stage'], 'failed'>];
  if (run.comparison_metrics) return 'comparison';
  if (run.pending_confirmation?.kind === 'revision' || run.pending_confirmation?.kind === 'findings' || run.findings?.length) return 'findings';
  if (run.baseline_metrics || run.traces?.length) return 'evidence';
  return 'input';
}

/** Retain actual public responses, including an action response before its fresh GET. */
export function retainSnapshot(previous: RunSnapshots, run: RunView): RunSnapshots {
  const step = stageView(run);
  const next = {...previous};
  // Keep richer historical contract/revision detail while an active stage omits it.
  if (!previous[step]?.pending_confirmation || run.pending_confirmation || !isPollingStage(run.stage)) next[step] = run;
  // A later review can carry the newly finished evidence for a view already seen.
  // Keep the whole actual response; never manufacture an earlier-stage response.
  if (previous.evidence && step === 'findings' && (run.baseline_metrics || run.traces?.length)) next.evidence = run;
  return next;
}
