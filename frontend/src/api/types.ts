/** Minimal engine contract types used by the temporary frontend adapter. */

export type ScenarioKind = 'normal' | 'boundary' | 'adversarial' | 'targeted';
export type Verdict = 'pass' | 'fail' | 'ambiguous' | 'error';
export type RunStatus =
  | 'pending'
  | 'ingesting'
  | 'extracting'
  | 'compiling'
  | 'compiled'
  | 'generating_scenarios'
  | 'scenarios_ready'
  | 'evaluating'
  | 'rehearsing'
  | 'completed'
  | 'failed';

export type Citation = {
  document_id: string;
  page?: number | null;
  section?: string | null;
  quote: string;
};

export type Predicate = {
  field: string;
  op?: string;
  value?: unknown;
};

export type Obligation = {
  modality: string;
  action: string;
  assignee?: string;
  details?: string;
};

export type Rule = {
  id: string;
  title: string;
  statement: string;
  citations?: Citation[];
  when?: Predicate[];
  then?: Obligation[];
  except_when?: Predicate[];
  parameters?: Record<string, unknown>;
  severity?: string;
  ambiguity?: string | null;
};

export type PolicyDocument = {
  document_id: string;
  filename: string;
  text?: string;
  page_count?: number;
};

export type PolicyIR = {
  policy_id: string;
  title: string;
  source: PolicyDocument;
  rules: Rule[];
  open_questions?: string[];
  conflicts?: string[];
  revision: number;
};

export type Scenario = {
  scenario_id: string;
  kind: ScenarioKind;
  title: string;
  narrative?: string;
  facts?: Record<string, unknown>;
  targeted_rule_ids?: string[];
  expected_outcome?: string | null;
  notes?: string;
};

export type ScenarioSuite = {
  suite_id: string;
  policy_id: string;
  policy_revision: number;
  scenarios: Scenario[];
};

export type TraceStep = {
  rule_id: string;
  matched: boolean;
  detail?: string;
};

export type EngineFinding = {
  finding_id: string;
  scenario_id: string;
  verdict: Verdict;
  rule_ids?: string[];
  summary: string;
  traces?: TraceStep[];
};

export type EvaluationReport = {
  report_id: string;
  policy_id: string;
  policy_revision: number;
  suite_id: string;
  findings: EngineFinding[];
  metrics?: Record<string, unknown>;
};

export type RevisionHint = {
  rule_ids?: string[];
  action: string;
  summary: string;
};

export type PolicyEffectivenessReport = {
  report_id: string;
  policy_id: string;
  policy_revision: number;
  score: number;
  justification: string;
  recommended_actions?: RevisionHint[];
  swarm_used?: boolean;
  metrics?: Record<string, unknown>;
};

export type AudienceSegment = {
  id: string;
  label?: string;
  weight?: number;
  attributes?: Record<string, unknown>;
};

export type SeedSpec = {
  text?: string;
  population_size?: number | null;
  groups?: string[];
  segments?: AudienceSegment[];
  locale?: string;
};

export type RunRecord = {
  run_id: string;
  status: RunStatus;
  message?: string;
  error?: string | null;
  seed?: SeedSpec;
  document?: PolicyDocument | null;
  ir?: PolicyIR | null;
  suite?: ScenarioSuite | null;
  evaluation?: EvaluationReport | null;
  effectiveness?: PolicyEffectivenessReport | null;
  created_at?: string;
  updated_at?: string;
};

export type CreateRunInput = {
  policyText: string;
  title?: string;
  seedText?: string;
  populationSize?: number;
  groups?: string[];
  segments?: AudienceSegment[];
  locale?: string;
};

/** UI shapes aligned with preview.ts field names. */
export type UiRule = {
  id: string;
  title: string;
  condition: string;
  effect: string;
  quote: string;
  section: string;
};

export type UiFinding = {
  title: string;
  type: string;
  level: string;
  scenario: string;
  rule: string;
  facts: string;
  expected: string;
  observed: string;
  quote: string;
  section: string;
  before: string;
  after: string;
  draft: string;
  trace: string[];
};

export type UiScenario = {
  id: string;
  category: string;
  facts: string;
  outcome: string;
  assertion: string;
  finding: number | null;
};

export type RunView = {
  runId: string;
  policyId: string;
  policyTitle: string;
  revision: number;
  suiteId: string;
  score: number | null;
  justification: string;
  recommendedActions: string[];
  openQuestions: string[];
  conflicts: string[];
  rules: UiRule[];
  scenarios: UiScenario[];
  findings: UiFinding[];
  ruleCount: number;
  scenarioCount: number;
  failCount: number;
  passCount: number;
  swarmUsed: boolean;
};
