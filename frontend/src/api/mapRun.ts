import type {
  EngineFinding,
  Obligation,
  Predicate,
  Rule,
  RunRecord,
  RunView,
  Scenario,
  UiFinding,
  UiRule,
  UiScenario,
} from './types';

function formatPredicate(p: Predicate): string {
  const op = p.op ?? 'eq';
  const value = typeof p.value === 'string' ? p.value : JSON.stringify(p.value);
  return `${p.field} ${op} ${value}`;
}

function formatObligation(o: Obligation): string {
  const details = o.details ? ` · ${o.details}` : '';
  return `${o.modality} ${o.action}${details}`;
}

function formatFacts(facts: Record<string, unknown> | undefined): string {
  if (!facts || Object.keys(facts).length === 0) return 'No structured facts';
  return Object.entries(facts)
    .map(([key, value]) => `${key}=${typeof value === 'string' ? value : JSON.stringify(value)}`)
    .join('; ');
}

function kindLabel(kind: string): string {
  if (kind === 'boundary') return 'Boundary';
  if (kind === 'adversarial') return 'Adversarial';
  if (kind === 'targeted') return 'Adversarial';
  return 'Normal';
}

function verdictType(verdict: string): string {
  if (verdict === 'fail') return 'Failure';
  if (verdict === 'ambiguous') return 'Ambiguous';
  if (verdict === 'error') return 'Error';
  return 'Pass';
}

function mapRule(rule: Rule): UiRule {
  const citation = rule.citations?.[0];
  const condition = rule.when?.length ? rule.when.map(formatPredicate).join(' AND ') : 'always';
  const effect = rule.then?.length ? rule.then.map(formatObligation).join(' · ') : rule.statement;
  return {
    id: rule.id,
    title: rule.title || rule.id,
    condition,
    effect,
    quote: citation?.quote || rule.statement,
    section: citation?.section || (citation?.page != null ? `p.${citation.page}` : '—'),
  };
}

function findingForScenario(
  scenarioId: string,
  evaluationFindings: EngineFinding[],
): EngineFinding | undefined {
  return evaluationFindings.find((f) => f.scenario_id === scenarioId);
}

function mapScenario(
  scenario: Scenario,
  evaluationFindings: EngineFinding[],
  reviewableIds: string[],
): UiScenario {
  const finding = findingForScenario(scenario.scenario_id, evaluationFindings);
  const assertion =
    finding?.verdict === 'pass'
      ? 'Passed'
      : finding
        ? 'Failed'
        : scenario.expected_outcome === 'compliant'
          ? 'Passed'
          : 'Failed';
  const outcome =
    finding?.verdict === 'pass'
      ? 'Resolved'
      : finding?.verdict === 'ambiguous'
        ? 'Ambiguous'
        : finding?.verdict === 'error'
          ? 'Error'
          : finding
            ? 'Failed'
            : scenario.expected_outcome || 'Resolved';
  const reviewIndex = finding && finding.verdict !== 'pass' ? reviewableIds.indexOf(finding.finding_id) : -1;
  return {
    id: scenario.scenario_id,
    category: kindLabel(scenario.kind),
    facts: scenario.narrative || formatFacts(scenario.facts) || scenario.title,
    outcome: String(outcome),
    assertion,
    finding: reviewIndex >= 0 ? reviewIndex : null,
  };
}

function mapFinding(
  finding: EngineFinding,
  scenariosById: Map<string, Scenario>,
  rulesById: Map<string, Rule>,
  hints: string[],
): UiFinding {
  const scenario = scenariosById.get(finding.scenario_id);
  const ruleIds = finding.rule_ids?.length ? finding.rule_ids : scenario?.targeted_rule_ids || [];
  const primaryRule = ruleIds[0] ? rulesById.get(ruleIds[0]) : undefined;
  const citation = primaryRule?.citations?.[0];
  const hint = hints.find((h) => ruleIds.some((id) => h.includes(id))) || hints[0] || finding.summary;
  const traces =
    finding.traces?.map((t) => `${t.rule_id}: ${t.matched ? 'matched' : 'not matched'}${t.detail ? ` — ${t.detail}` : ''}`) ||
    [];

  return {
    title: finding.summary.slice(0, 120) || scenario?.title || finding.finding_id,
    type: verdictType(finding.verdict),
    level: 'Engine evaluation',
    scenario: finding.scenario_id,
    rule: ruleIds.join(' · ') || '—',
    facts: scenario?.narrative || formatFacts(scenario?.facts) || scenario?.title || finding.summary,
    expected: scenario?.expected_outcome || 'Policy constraints should hold for this scenario.',
    observed: finding.summary,
    quote: citation?.quote || primaryRule?.statement || finding.summary,
    section: citation?.section || '—',
    before: primaryRule ? `${primaryRule.id}: ${primaryRule.statement}` : finding.summary,
    after: hint,
    draft: hint,
    trace: traces.length ? traces : [finding.summary],
  };
}

export function mapRunToView(run: RunRecord): RunView {
  const ir = run.ir;
  const suite = run.suite;
  const evaluation = run.evaluation;
  const effectiveness = run.effectiveness;

  const rules = (ir?.rules || []).map(mapRule);
  const rulesById = new Map((ir?.rules || []).map((r) => [r.id, r]));
  const scenariosById = new Map((suite?.scenarios || []).map((s) => [s.scenario_id, s]));

  const evalFindings = evaluation?.findings || [];
  const reviewable = evalFindings.filter((f) => f.verdict !== 'pass');
  // If everything passed, surface recommended actions as reviewable cards when present.
  const reviewSource =
    reviewable.length > 0
      ? reviewable
      : (effectiveness?.recommended_actions || []).map(
          (action, index): EngineFinding => ({
            finding_id: `hint_${index}`,
            scenario_id: suite?.scenarios[0]?.scenario_id || `scn_hint_${index}`,
            verdict: 'ambiguous',
            rule_ids: action.rule_ids || [],
            summary: action.summary,
            traces: [],
          }),
        );

  const reviewableIds = reviewSource.map((f) => f.finding_id);
  const hintTexts = (effectiveness?.recommended_actions || []).map((a) => a.summary);

  const findings = reviewSource.map((f) => mapFinding(f, scenariosById, rulesById, hintTexts));
  const scenarios = (suite?.scenarios || []).map((s) => mapScenario(s, evalFindings, reviewableIds));

  const passCount = evalFindings.filter((f) => f.verdict === 'pass').length;
  const failCount = evalFindings.filter((f) => f.verdict !== 'pass').length;

  return {
    runId: run.run_id,
    policyId: ir?.policy_id || '—',
    policyTitle: ir?.title || run.document?.filename || 'Untitled policy',
    revision: ir?.revision ?? 1,
    suiteId: suite?.suite_id || '—',
    score: effectiveness?.score ?? null,
    justification: effectiveness?.justification || '',
    recommendedActions: hintTexts,
    openQuestions: ir?.open_questions || [],
    conflicts: ir?.conflicts || [],
    rules,
    scenarios,
    findings,
    ruleCount: rules.length,
    scenarioCount: scenarios.length,
    failCount,
    passCount,
    swarmUsed: Boolean(effectiveness?.swarm_used),
  };
}

export function buildSeedText(input: {
  goals: string[];
  assumptions: { text: string; source: string; confirmed: boolean }[];
}): string {
  const goals = input.goals.filter((g) => g.trim()).map((g, i) => `Goal ${i + 1}: ${g.trim()}`);
  const assumptions = input.assumptions
    .filter((a) => a.text.trim())
    .map(
      (a, i) =>
        `Assumption ${i + 1}${a.confirmed ? ' (confirmed)' : ''}: ${a.text.trim()} [${a.source.trim() || 'unspecified'}]`,
    );
  return [...goals, ...assumptions].join('\n');
}

export function buildRevisionInstruction(
  findings: UiFinding[],
  acceptedIndexes: number[],
  intents: string[],
): string {
  const accepted = acceptedIndexes
    .map((i) => findings[i])
    .filter(Boolean)
    .map((f, n) => `${n + 1}. Fix finding "${f.title}" (${f.scenario}): ${f.observed}. Suggested: ${f.after}`);
  const intentLines = intents.filter((t) => t.trim()).map((t, i) => `Intent ${i + 1}: ${t.trim()}`);
  return [...accepted, ...intentLines].join('\n') || 'Tighten the policy based on failed evaluation findings.';
}
