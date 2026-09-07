import type { AgentSimulationResult } from '../api/transport';

export function AgentEvidenceView({ result, step = 'evidence' }: { result: AgentSimulationResult; step?: 'evidence' | 'findings' | 'comparison' }) {
  const title = step === 'findings' ? 'Agent findings' : step === 'comparison' ? 'Agent comparison' : 'Agent conversation evidence';
  const interactionVerified = result.effectiveness?.interaction_verified ?? Boolean(result.extra?.swarm?.interaction_verified);
  const subtitle = step === 'findings' ? 'Potential policy gaps identified by the fuzz and swarm agents.' : step === 'comparison' ? 'Agent-backed effectiveness result for the simulated policy.' : interactionVerified ? 'Verified agent-to-agent replies from the MiroFish simulation.' : 'MiroFish captured agent posts, but no agent-to-agent replies were returned.';
  const swarm = result.extra?.swarm;
  const posts = swarm?.posts ?? [];
  const comments = swarm?.comments ?? [];
  const actions = swarm?.actions ?? [];
  const normalizeTurn = (item: { agent?: string; user_name?: string; agent_name?: string; user_id?: string | number; text?: string; content?: string; kind?: string; why_significant?: string }) => ({
    agent: item.agent ?? item.user_name ?? item.agent_name ?? (item.user_id !== undefined ? `MiroFish agent ${Number(item.user_id) + 1}` : 'MiroFish agent'),
    text: item.text ?? item.content ?? '',
    kind: item.kind ?? 'post',
    why: item.why_significant ?? '',
  });
  const conversation = [...posts.map(normalizeTurn), ...comments.map(normalizeTurn), ...actions.map((item) => normalizeTurn({
    agent: item.agent,
    agent_name: item.agent_name,
    text: item.text,
    content: item.content,
    user_id: typeof item.user_id === 'string' || typeof item.user_id === 'number' ? item.user_id : undefined,
    kind: typeof item.kind === 'string' ? item.kind : 'action',
    why_significant: typeof item.why_significant === 'string' ? item.why_significant : undefined,
  }))]
    .filter((item) => item.text.trim().length > 0);
  const structuredHighlights = (result.effectiveness?.highlights ?? [])
    .map((item) => normalizeTurn(item))
    .filter((item) => item.text.trim().length > 0);
  const seen = new Set<string>();
  const highlights = [...structuredHighlights, ...conversation]
    .filter((item) => {
      const key = `${item.agent}\u0000${item.text}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 6);
  const findings = result.evaluation?.findings ?? [];
  const metrics = result.effectiveness?.metrics ?? {};
  const verdicts = (metrics.verdicts as Record<string, unknown> | undefined) ?? {};
  const interactionCount = Number(metrics.swarm_posts ?? 0) + Number(metrics.swarm_comments ?? 0) + Number(metrics.swarm_actions ?? 0);
  const duplicateMessagesRejected = Number(swarm?.duplicate_messages_rejected ?? 0);
  const findingCounts = findings.reduce((counts, finding) => {
    const verdict = finding.verdict ?? 'unknown';
    counts[verdict] = (counts[verdict] ?? 0) + 1;
    return counts;
  }, {} as Record<string, number>);
  const failedFindings = findings.filter((finding) => finding.verdict === 'fail');
  const testedRules = [...new Set(findings.flatMap((finding) => finding.rule_ids ?? []))];
  const policySource = result.policy_source_text ?? result.document?.text ?? result.ir?.source?.text ?? '';
  const policyRules = result.ir?.rules ?? [];
  const testedRuleStatements = policyRules
    .filter((rule) => !testedRules.length || (rule.id && testedRules.includes(rule.id)))
    .map((rule) => ({ id: rule.id ?? 'policy clause', statement: rule.statement ?? '' }))
    .filter((rule) => rule.statement.trim().length > 0);
  const policyTextForMatching = `${result.policy_title ?? ''} ${policySource} ${testedRuleStatements.map((rule) => rule.statement).join(' ')}`;
  const isMajuForestPolicy = /maju\s+forest/i.test(policyTextForMatching);
  const policyLabel = result.policy_title || (isMajuForestPolicy ? 'Maju Forest redevelopment policy' : result.ir?.title || result.document?.filename || 'this policy');
  const ruleIdExplanation = result.compatibility_mode
    ? `${testedRules.join(' and ') || 'These IDs'} are MiroFish trace labels generated while it parsed the source. They are not policy clauses or eligibility requirements that you were expected to write.`
    : testedRules.length
      ? `${testedRules.join(' and ')} is a PolicyFuzz-generated trace ID, not a label you were expected to provide. It links each finding back to the policy text.`
      : 'PolicyFuzz-generated rule IDs are trace labels used to link findings back to the policy text; they are not labels you were expected to provide.';
  const findingsSummary = step === 'findings' ? <section className="panel"><h3>What these fuzz-agent findings mean</h3><p>PolicyFuzz ran {findings.length} independent fuzz-agent scenarios against {testedRules.length || 'the tested'} rule{testedRules.length === 1 ? '' : 's'}{testedRules.length ? ` (${testedRules.join(', ')})` : ''} from <strong>{policyLabel}</strong>. The agents deliberately included normal, boundary, adversarial, and targeted cases so the policy is tested beyond its happy path.</p><div className="inset"><h4>What the agents actually tested</h4><p>These trace labels point back to the source text; they are not extra requirements.</p>{testedRuleStatements.length > 0 ? <ul>{testedRuleStatements.slice(0, 4).map((rule) => <li key={rule.id}><strong>{rule.id}:</strong> {rule.statement}</li>)}</ul> : <p>{policySource ? policySource.slice(0, 700) : 'The source policy text was not included in this result.'}</p>}</div><div className="inset"><h4>What is {testedRules.join(' and ') || 'this rule ID'}?</h4><p>{ruleIdExplanation}</p></div><div className="aggregate-grid"><div><span className="eyebrow">Passed</span><strong>{findingCounts.pass ?? 0}</strong></div><div><span className="eyebrow">Failed</span><strong>{findingCounts.fail ?? 0}</strong></div><div><span className="eyebrow">Ambiguous</span><strong>{findingCounts.ambiguous ?? 0}</strong></div><div><span className="eyebrow">Score</span><strong>{result.effectiveness?.score ?? 'N/A'}/100</strong></div></div><h4>Policy assessment</h4>{failedFindings.length > 0 ? <><p>{isMajuForestPolicy ? <>The Maju Forest policy is not being tested against a different policy. The mismatches point to specific gaps in the stated redevelopment safeguards: {failedFindings.length} fuzz agent{failedFindings.length === 1 ? '' : 's'} expected a violation or an ambiguous outcome, but the current wording treated the scenario as compliant.</> : <>The policy is currently too broad or underspecified around exceptions and edge cases. {failedFindings.length} fuzz agent{failedFindings.length === 1 ? '' : 's'} expected a violation or an ambiguous outcome, but the policy treated the scenario as compliant.</>} This means the rule may accept cases it should reject, while failing to tell users what happens when eligibility, authority, or an exception is unclear.</p><div className="inset"><h4>How to improve {isMajuForestPolicy ? 'the Maju Forest policy' : 'the policy'}</h4>{isMajuForestPolicy ? <><p>Clarify the policy’s own safeguards before adding anything new:</p><ul><li>define who may authorize Maju Forest redevelopment and what counts as an eligible housing or public-facility project;</li><li>define what makes the environmental impact assessment sufficient, how the 30% protected-forest threshold is measured, and who verifies it;</li><li>specify who must receive notice, the minimum notice period, how the public hearing is conducted, and how objections affect the decision;</li><li>define “immediate safety risk,” who may invoke the emergency exception, what work is allowed, and what happens if the 14-day report is late or incomplete.</li></ul></> : <><p>Rewrite the broad statement as separate, numbered requirements. For each requirement, state:</p><ul><li>who is eligible or responsible;</li><li>what action is required, allowed, or prohibited;</li><li>which exceptions apply and what happens when eligibility is unclear;</li><li>what causes a rejection, and how a person can appeal or request review.</li></ul></>}<p>These are clarification prompts grounded in the submitted policy—not new housing, compensation, or eligibility rules. Rerun the fuzz suite after revising the source so adversarial cases are rejected and genuinely unclear cases remain ambiguous.</p></div><p><strong>Recommended next step:</strong> revise {testedRules.join(' and ') || 'the failing rule'} using the conditions above, then rerun the Maju Forest scenario suite.</p></> : <p>No fuzz-agent mismatches were found in this run. The tested cases behaved as expected; continue reviewing any open questions before treating the policy as complete.</p>}</section> : null;
  const compatibilityNotice = result.compatibility_mode ? <div className="notice"><strong>Custom-policy compatibility mode.</strong><span>MiroFish parsed this general policy directly because it is broader than PolicyFuzz’s typed travel-and-expense schema. IDs such as R001 are engine trace labels, not requirements added to your policy.</span></div> : null;
  const interactionNotice = !interactionVerified ? <div className="notice warning"><strong>Interaction not verified.</strong><span>MiroFish returned no reply/comment records, so this run is shown as a post capture rather than agent-to-agent conversation.</span></div> : null;
  const highlightSection = highlights.length > 0 ? <section className="panel"><div className="row"><h3>Featured conversation highlights</h3><span className="badge success">{highlights.length} selected</span></div><p className="muted small">High-signal moments selected from the MiroFish capture, including agent reactions and policy concerns.</p><div className="agent-highlights">{highlights.map((item, index) => <article className="inset" key={`${item.agent}-${index}`}><div className="row"><strong>{item.agent}</strong><span className="badge">{item.kind}</span></div><p>{item.text}</p>{item.why ? <small className="muted">Why it matters: {item.why}</small> : null}</article>)}</div></section> : null;
  return <div className="content" id="agent-evidence"><section className="page-title"><div><span className="eyebrow">Step {step === 'evidence' ? 2 : step === 'findings' ? 3 : 4} · MiroFish</span><h2>{title}</h2><p>{subtitle}</p></div></section><section className="metrics"><article className="panel"><span className="eyebrow">Status</span><div className="metric">{result.status}</div></article><article className="panel"><span className="eyebrow">Effectiveness</span><div className="metric">{result.effectiveness?.score ?? 'N/A'}<small>/100</small></div></article><article className="panel"><span className="eyebrow">MiroFish run</span><div className="metric"><code>{result.run_id}</code></div></article></section>{compatibilityNotice}{interactionNotice}{duplicateMessagesRejected > 0 ? <p className="muted small">{duplicateMessagesRejected} duplicate message{duplicateMessagesRejected === 1 ? '' : 's'} filtered from the public evidence.</p> : null}{step === 'evidence' ? <>{highlightSection}<section className="panel"><div className="row"><h3>Full agent conversation timeline</h3><span className="badge">{conversation.length} turns</span></div><div className="agent-conversation">{conversation.map((item, index) => <article className="inset" key={`${item.agent}-${index}`}><div className="row"><strong>{item.agent}</strong><span className="badge">{item.kind}</span></div><p>{item.text}</p></article>)}{conversation.length === 0 ? <p>No non-empty conversation turns were returned by MiroFish.</p> : null}</div></section></> : null}{step === 'findings' ? <>{findingsSummary}{highlightSection}<section className="panel"><h3>Agent findings</h3><div className="agent-findings">{findings.map((finding, index) => <article className="inset" key={index}><div className="row"><strong>{finding.verdict ?? 'finding'}</strong><code>{finding.scenario_id ?? `finding-${index + 1}`}</code></div><p>{finding.summary ?? 'No finding summary returned.'}</p>{finding.rule_ids?.length ? <small>Rules: {finding.rule_ids.join(', ')}</small> : null}</article>)}{findings.length === 0 ? <p>No structured findings were returned by the rehearsal engine.</p> : null}</div></section></> : null}{step === 'comparison' ? <><section className="panel"><h3>Simulation outcome</h3><p>Final agent-backed effectiveness score: <strong>{result.effectiveness?.score ?? 'N/A'}/100</strong></p><div className="aggregate-grid"><div><span className="eyebrow">Agent interactions</span><strong>{interactionCount}</strong></div><div><span className="eyebrow">Reply verification</span><strong>{interactionVerified ? 'verified' : 'not verified'}</strong></div><div><span className="eyebrow">Fuzz pass</span><strong>{String(verdicts.pass ?? '—')}</strong></div><div><span className="eyebrow">Fuzz fail</span><strong>{String(verdicts.fail ?? '—')}</strong></div><div><span className="eyebrow">Ambiguous</span><strong>{String(verdicts.ambiguous ?? '—')}</strong></div></div></section>{highlightSection}<section className="panel"><h3>Detailed outcome</h3><div className="agent-outcome">{result.effectiveness?.justification ?? result.message ?? 'No comparison summary was returned.'}</div></section></> : null}</div>;
}
