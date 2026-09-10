import type { AgentSimulationResult } from '../api/transport';
import { majuForestDemo } from '../fixtures/majuForestDemo';

type Turn = { agent: string; text: string; kind: string; why?: string };
const hasText = (turn: Turn) => turn.text.trim().length > 0;

function normalizeTurn(item: { agent?: string; user_name?: string; text?: string; content?: string }, kind: string): Turn {
  return { agent: item.agent || item.user_name || 'Unnamed simulation agent', text: item.text || item.content || '', kind };
}

export function AgentEvidenceView({ result, step = 'evidence' }: { result: AgentSimulationResult; step?: 'evidence' | 'findings' | 'comparison' }) {
  const title = step === 'findings' ? 'Candidate agent observations' : step === 'comparison' ? 'Exploratory simulation summary' : 'Agent conversation evidence';
  const swarm = result.extra?.swarm;
  const posts = (swarm?.posts ?? []).map((item) => normalizeTurn(item, 'post')).filter(hasText);
  const comments = (swarm?.comments ?? []).map((item) => normalizeTurn(item, 'reply/comment')).filter(hasText);
  const actions = (swarm?.actions ?? []).map((item) => normalizeTurn({ ...item, agent: item.agent || item.agent_name }, 'action')).filter(hasText);
  const conversation = [...posts, ...comments, ...actions];
  const structuredHighlights: Turn[] = (result.effectiveness?.highlights ?? []).map((item) => ({
    ...normalizeTurn(item, item.kind || 'excerpt'), why: item.why_significant,
  })).filter(hasText);
  const seen = new Set<string>();
  const highlights = [...structuredHighlights, ...conversation].filter((item) => {
    const key = JSON.stringify([item.agent, item.text]);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 6);
  const findings = result.evaluation?.findings ?? [];
  const referencedRules = new Set(findings.flatMap((finding) => finding.rule_ids ?? []));
  const ruleStatements = (result.ir?.rules ?? [])
    .filter((rule) => !referencedRules.size || (rule.id !== undefined && referencedRules.has(rule.id)))
    .filter((rule) => rule.statement?.trim());
  const policySource = result.policy_source_text || result.document?.text || result.ir?.source?.text;
  const policyLabel = result.policy_title || result.ir?.title || result.document?.filename || 'Untitled policy';
  const hypotheticalDemo = policyLabel === majuForestDemo.title || policySource?.includes(majuForestDemo.notice);
  const reportedCounts = ['pass', 'fail', 'ambiguous'].map((label) => ({ label, count: findings.filter((finding) => finding.verdict === label).length }));
  const duplicates = swarm?.duplicate_messages_rejected ?? 0;
  const interactionClaim = result.effectiveness?.interaction_verified ?? swarm?.interaction_verified;
  const score = result.effectiveness?.metrics?.score_available === false ? 'Not scored' : (result.effectiveness?.score ?? 'Unavailable');

  const highlightSection = highlights.length ? <section className="panel">
    <div className="row"><h3>Returned conversation excerpts</h3><span className="badge">{highlights.length} excerpts</span></div>
    <p className="muted small">Provider highlights and captured messages, deduplicated for display. These are unverified agent statements.</p>
    <div className="agent-highlights">{highlights.map((item, index) => <article className="inset" key={index}>
      <div className="row"><strong>{item.agent}</strong><span className="badge">{item.kind}</span></div>
      <p>{item.text}</p>{item.why ? <small className="muted">Agent-provided context: {item.why}</small> : null}
    </article>)}</div>
  </section> : null;

  return <div className="content" id="agent-evidence">
    <section className="page-title"><div><span className="eyebrow">MiroFish · exploratory simulation</span><h2>{title}</h2><p>{policyLabel}</p></div></section>
    {hypotheticalDemo ? <div className="notice warning" role="note"><strong>{majuForestDemo.notice}</strong><span>Dates, figures, agency actions and environmental claims are unverified scenario premises.</span></div> : null}
    <div className="notice warning" role="note"><strong>Exploratory simulation — unverified</strong><span>Agent observations, reported labels, and heuristic scores are not deterministic verdicts. They do not establish policy correctness, confirmed defects, or revision acceptance.</span></div>
    <p className="notice">Simulated participants do not speak for real people or agencies. Their statements are not a representative survey or a prediction of public opinion.</p>
    <section className="metrics">
      <article className="panel"><span className="eyebrow">Provider status</span><div className="metric">{result.status}</div></article>
      <article className="panel"><span className="eyebrow">Heuristic score</span><div className="metric">{score}</div><p className="muted small">Provider-reported; not a validated pass rate.</p></article>
      <article className="panel"><span className="eyebrow">MiroFish run</span><div className="metric"><code>{result.run_id}</code></div></article>
    </section>
    {result.compatibility_mode ? <div className="notice"><strong>Custom-policy compatibility mode.</strong><span>This exploratory result does not use PolicyFuzz’s confirmed travel-and-expense rule contract. General policy observations require separate review.</span></div> : null}
    {result.error || swarm?.error ? <div className="notice warning"><strong>Simulation capture may be incomplete.</strong><span>The simulation reported an error. Review the available records before drawing conclusions.</span></div> : null}
    <div className="notice"><strong>Conversation capture</strong><span>{comments.length ? `${comments.length} reply/comment record${comments.length === 1 ? '' : 's'} returned.` : 'No reply/comment records were returned; posts alone do not establish agent-to-agent dialogue.'} Captured identities and reply relationships are not independently authenticated.{interactionClaim !== undefined ? ` Provider interaction flag: ${interactionClaim ? 'true' : 'false'}.` : ''}</span></div>
    {duplicates > 0 ? <p className="muted small">Provider reports {duplicates} duplicate messages filtered from its capture.</p> : null}
    {step === 'evidence' ? <>{highlightSection}<section className="panel">
      <div className="row"><h3>Captured agent messages</h3><span className="badge">{conversation.length} messages</span></div>
      <p className="muted small">Grouped by posts, replies/comments, and actions; timestamps and reply links are not supplied in this view.</p>
      <div className="agent-conversation">{conversation.map((item, index) => <article className="inset" key={index}>
        <div className="row"><strong>{item.agent}</strong><span className="badge">{item.kind}</span></div><p>{item.text}</p>
      </article>)}</div>
      {!conversation.length ? <p>No non-empty conversation messages were returned by MiroFish.</p> : null}
    </section></> : null}
    {step === 'findings' ? <>
      <section className="panel"><h3>Review the reported observations</h3>
        <p>{findings.length} observation record{findings.length === 1 ? '' : 's'} returned for <strong>{policyLabel}</strong>. The response does not establish independent expected answers, coverage, or a reproducible defect count.</p>
        <div className="aggregate-grid">{reportedCounts.map(({ label, count }) => <div key={label}><span className="eyebrow">Reported {label}</span><strong>{count}</strong></div>)}</div>
        <div className="inset"><h4>Reported rule text</h4><p>Rule IDs are provider trace labels. A label alone does not verify a source citation or a confirmed executable rule.</p>
          {ruleStatements.length ? <ul>{ruleStatements.map((rule, index) => <li key={index}><strong>{rule.id || 'Unnamed trace'}: </strong><span>{rule.statement}</span></li>)}</ul> : <p>No matching rule statements were included.</p>}
          {policySource ? <details><summary>Returned policy source</summary><p>{policySource}</p></details> : <p>Source policy text was not included in this result.</p>}
        </div>
        <p>Review each observation against the source and confirm the intended behavior before turning it into a deterministic test. No policy revision is verified by this simulation.</p>
      </section>
      {highlightSection}
      <section className="panel"><h3>Observation details</h3><div className="agent-findings">{findings.map((finding, index) => <article className="inset" key={index}>
        <div className="row"><span className="badge">Candidate</span><strong>{finding.verdict || 'No reported label'}</strong><code>{finding.scenario_id || 'Scenario ID unavailable'}</code></div>
        <p>{finding.summary || 'No observation summary returned.'}</p>{finding.rule_ids?.length ? <small>Reported rule labels: {finding.rule_ids.join(', ')}</small> : <small>No rule references returned.</small>}
      </article>)}</div>{!findings.length ? <p>No structured observations were returned. This is not evidence that the policy has no defects.</p> : null}</section>
    </> : null}
    {step === 'comparison' ? <>
      <section className="panel"><h3>No verified before-and-after comparison</h3><p>This simulation response does not include a frozen suite and baseline/revised evaluation artifacts. A heuristic score cannot show that a change fixed defects or avoided regressions.</p><p>Use PolicyFuzz’s deterministic comparison after confirming a structured revision to inspect the same-suite result and acceptance checks.</p></section>
      {highlightSection}
      <section className="panel"><h3>Agent-provided assessment — unverified</h3><div className="agent-outcome">{result.effectiveness?.justification || result.message || 'No assessment was returned.'}</div></section>
    </> : null}
  </div>;
}
