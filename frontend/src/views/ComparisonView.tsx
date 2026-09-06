import { AlertTriangle, Check, Fingerprint, ShieldCheck, X } from 'lucide-react';
import type { RunView } from '../api/types';
import { HashValue } from '../components/HashValue';
import { OutcomeBadge } from '../components/OutcomeBadge';

export interface ComparisonViewProps { run: RunView }

const effectStates = ['VALUE', 'GAP', 'NOT_APPLICABLE', 'CONFLICT', 'INCONCLUSIVE', 'ERROR'] as const;
const transitionCategories = ['fail_to_pass', 'fail_to_fail', 'pass_to_pass', 'pass_to_fail', 'inconclusive_or_error'] as const;

function BooleanGate({ label, passed }: { label: string; passed: boolean }) {
  return <li aria-label={`Acceptance gate ${label}`} className={passed ? 'gate-pass' : 'gate-fail'}>{passed ? <Check aria-hidden="true" /> : <X aria-hidden="true" />}<div><strong>{label}</strong><small>{passed ? 'Passed' : 'Failed'}</small></div></li>;
}

export function ComparisonView({ run }: ComparisonViewProps) {
  const comparison = run.comparison_metrics;
  if (!comparison) {
    return <div className="content"><section className="page-title"><div><span className="eyebrow">Step 4</span><h2>Comparison</h2></div></section><section className="panel"><h3>Comparison unavailable</h3><p>Before-and-after public metrics are unavailable in the current snapshot.</p></section></div>;
  }
  const acceptance = comparison.acceptance;
  const holdout = run.holdout_evidence;
  const gates: Array<[string, boolean]> = [
    ['Same frozen suite hash', acceptance.suite_hash_matches],
    ['All target findings fixed', acceptance.all_target_findings_fixed],
    ['Zero new failures outside targets', acceptance.zero_new_failures_outside_targets],
    ['Zero protected regressions', acceptance.zero_protected_regressions],
    ['No increase in gaps, conflicts, inconclusive results, or errors', acceptance.no_increase_in_gap_conflict_inconclusive_or_error],
    ['Unrelated rules unchanged', acceptance.unrelated_rules_unchanged],
    ['Aggregate holdout not worse', acceptance.holdout_not_worse],
  ];

  return (
    <div className="content">
      <section className="page-title"><div><span className="eyebrow">Step 4</span><h2>Comparison</h2><p>Deterministic baseline and revision aggregates over the frozen suite.</p></div></section>
      <section className={`panel result-banner ${comparison.patch_accepted ? '' : 'result-failed'}`}>
        <span className="iconbox">{comparison.patch_accepted ? <ShieldCheck aria-hidden="true" /> : <AlertTriangle aria-hidden="true" />}</span>
        <div>{comparison.patch_accepted ? <h3 data-tone="success">Revision passed every safeguard</h3> : <h3 data-tone="danger">Revision did not pass all safeguards</h3>}<p>{comparison.patch_accepted ? 'The public patch acceptance report records every gate as passed.' : 'The proposed revision remains rejected. Review failed gates before any further action.'}</p></div>
      </section>

      <section className="panel">
        <h3>Effect state comparison</h3>
        <div className="table-scroll" role="region" aria-label="Effect state comparison" tabIndex={0}><table><thead><tr><th>Effect state</th><th>Baseline</th><th>Revised</th></tr></thead><tbody>{effectStates.map((state) => <tr key={state} aria-label={`Effect state ${state}`}><th scope="row">{state.replaceAll('_', ' ')}</th><td>{comparison.baseline.effect_states[state]}</td><td>{comparison.revised.effect_states[state]}</td></tr>)}</tbody></table></div>
      </section>

      <div className="two-col">
        <section className="panel"><h3>Assertion metrics</h3><div className="comparison-metrics"><div><span className="eyebrow">Baseline pass percent</span><strong>{comparison.baseline.assertion_pass_percent === null ? 'N/A' : `${comparison.baseline.assertion_pass_percent}%`}</strong></div><div><span className="eyebrow">Revised pass percent</span><strong>{comparison.revised.assertion_pass_percent === null ? 'N/A' : `${comparison.revised.assertion_pass_percent}%`}</strong></div></div></section>
        <section className="panel"><h3>Regression counts</h3><div className="comparison-metrics"><div><span className="eyebrow">Protected regressions</span><strong>{comparison.protected_regressions}</strong></div><div><span className="eyebrow">New failures outside targets</span><strong>{comparison.new_failures_outside_targets}</strong></div></div></section>
      </div>

      <section className="panel">
        <h3>Assertion transitions</h3>
        <div className="table-scroll" role="region" aria-label="Aggregate assertion transitions" tabIndex={0}><table><thead><tr><th>Assertion transition</th><th>Count</th></tr></thead><tbody>{transitionCategories.map((category) => <tr key={category} aria-label={`Assertion transition ${category}`}><th scope="row">{category.replaceAll('_', ' ')}</th><td>{comparison.assertion_transition_counts[category]}</td></tr>)}</tbody></table></div>
        <p className="notice neutral">Item-level transition IDs are unavailable in this public view.</p>
      </section>

      <section className="panel"><div className="section-heading"><span className="iconbox"><ShieldCheck aria-hidden="true" /></span><h3>Patch acceptance gates</h3></div><ul className="gates">{gates.map(([label, passed]) => <BooleanGate key={label} label={label} passed={passed} />)}</ul>{acceptance.counts ? <div className="aggregate-grid"><div><span>Fixed target findings</span><strong>{acceptance.counts.fixed_target_findings} / {acceptance.counts.target_findings}</strong></div><div><span>Unrelated rule changes</span><strong>{acceptance.counts.unrelated_rule_changes}</strong></div><div><span>Holdout regressions</span><strong>{acceptance.counts.holdout_regressions}</strong></div></div> : null}</section>

      <section className="panel hash-comparison"><div className="section-heading"><span className="iconbox"><Fingerprint aria-hidden="true" /></span><h3>Frozen comparison inputs</h3></div><div className="two-col"><div><h4>Baseline</h4><HashValue label="Policy hash" value={acceptance.baseline_inputs.policy_sha256} /><HashValue label="Contract hash" value={acceptance.baseline_inputs.contract_sha256} /><HashValue label="Suite hash" value={acceptance.baseline_inputs.suite_sha256} /><HashValue label="Engine hash" value={acceptance.baseline_inputs.engine_sha256} /><HashValue label="Run manifest hash" value={acceptance.baseline_inputs.run_manifest_sha256} /></div><div><h4>Revised</h4><HashValue label="Policy hash" value={acceptance.revised_inputs.policy_sha256} /><HashValue label="Contract hash" value={acceptance.revised_inputs.contract_sha256} /><HashValue label="Suite hash" value={acceptance.revised_inputs.suite_sha256} /><HashValue label="Engine hash" value={acceptance.revised_inputs.engine_sha256} /><HashValue label="Run manifest hash" value={acceptance.revised_inputs.run_manifest_sha256} /></div></div></section>

      <section className="panel" aria-label="Aggregate holdout evidence"><h3>Aggregate holdout evidence</h3>{holdout ? <><div className="aggregate-grid"><div><span>Scenarios</span><strong>{holdout.scenario_count ?? 0}</strong></div><div><span>Rejected scenarios</span><strong>{holdout.rejected_scenario_count ?? 0}</strong></div><div><span>Rejected rules</span><strong>{holdout.rejected_rule_count ?? 0}</strong></div><div><span>Unsupported clauses</span><strong>{holdout.unsupported_clause_count ?? 0}</strong></div></div>{holdout.baseline_effect_states ? null : <p>Baseline holdout effect-state counts are unavailable in this public snapshot.</p>}<div className="table-scroll" role="region" aria-label="Holdout effect state aggregates" tabIndex={0}><table><thead><tr><th>Effect state</th><th>Baseline</th><th>Revised</th></tr></thead><tbody>{effectStates.map((state) => <tr key={state}><th scope="row">{state.replaceAll('_', ' ')}</th><td>{holdout.baseline_effect_states ? holdout.baseline_effect_states[state] ?? 0 : 'N/A'}</td><td>{holdout.revised_effect_states?.[state] ?? 'N/A'}</td></tr>)}</tbody></table></div></> : <p>Aggregate holdout evidence is unavailable in this public snapshot.</p>}</section>
    </div>
  );
}
