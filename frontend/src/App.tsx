import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  ShieldCheck,
  Trash2,
  ArrowRight,
  Check,
  ChevronRight,
  FileText,
  FlaskConical,
  AlertTriangle,
  Code2,
  Fingerprint,
  X,
  Plus,
  Activity,
  LockKeyhole,
  CircleCheck,
  Layers,
  Download,
} from 'lucide-react';
import {
  SetupEditor,
  BehaviorEvidence,
  BehavioralComparison,
  defaultContext,
  setupValid,
  type SimulationState,
  type SetupContext,
} from './behavior';
import {
  findings as mockFindings,
  gates,
  intents as initialIntents,
  policyText,
  rules as mockRules,
  scenarios as mockScenarios,
  stages,
} from './preview';
import { isHttpMode } from './api/config';
import { createRun, rehearseRun, reviseRun, EngineApiError } from './api/engineClient';
import { buildRevisionInstruction, buildSeedText, mapRunToView } from './api/mapRun';
import type { RunView, UiFinding, UiRule, UiScenario } from './api/types';

const steps = ['Setup & interpretation', 'Scenarios & behavior', 'Findings & revision', 'Comparison'];

function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: string }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
function Panel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}>{children}</section>;
}
function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <Panel>
      <span className="eyebrow">{label}</span>
      <div className="metric">{value}</div>
      <div className="meter">
        <span />
      </div>
      <p className="muted small">{detail}</p>
    </Panel>
  );
}

function Evidence({ finding, policyLabel }: { finding: UiFinding; policyLabel: string }) {
  return (
    <>
      <div className="inset">
        <span className="eyebrow">Scenario facts · {finding.scenario}</span>
        <p>{finding.facts}</p>
      </div>
      <div className="two-col">
        <div className="evidence expected">
          <span className="eyebrow">Expected behavior</span>
          <p>{finding.expected}</p>
          <small>Source: owner intent / required effect dimension</small>
        </div>
        <div className="evidence observed">
          <span className="eyebrow">Observed outcome</span>
          <p>{finding.observed}</p>
          <small>
            {isHttpMode ? 'Engine evaluation' : 'Illustrative baseline'} · {policyLabel}
          </small>
        </div>
      </div>
      <details className="inset" open>
        <summary>Applied rules & condition checks</summary>
        <ol className="trace">
          {finding.trace.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ol>
      </details>
      <div className="inset">
        <span className="eyebrow">
          Exact source quotation · Section {finding.section} · Page 1
        </span>
        <blockquote>“{finding.quote}”</blockquote>
        <code>
          {finding.rule} · {policyLabel}
        </code>
      </div>
    </>
  );
}

function emptyView(): RunView {
  return {
    runId: '',
    policyId: '—',
    policyTitle: '',
    revision: 1,
    suiteId: '—',
    score: null,
    justification: '',
    recommendedActions: [],
    openQuestions: [],
    conflicts: [],
    rules: [],
    scenarios: [],
    findings: [],
    ruleCount: 0,
    scenarioCount: 0,
    failCount: 0,
    passCount: 0,
    swarmUsed: false,
  };
}

export default function App() {
  const [comparisonCompatible, setComparisonCompatible] = useState(true);
  const [context, setContext] = useState<SetupContext>(defaultContext);
  const [simulationState, setSimulationState] = useState<SimulationState>('completed');
  const [step, setStep] = useState(0);
  const [reached, setReached] = useState(0);
  const [review, setReview] = useState(false);
  const [text, setText] = useState('');
  const [title, setTitle] = useState('APAC Travel & Expense Policy');
  const [ack, setAck] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [intents, setIntents] = useState(initialIntents);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [filter, setFilter] = useState('All');
  const [selected, setSelected] = useState(0);
  const [decisions, setDecisions] = useState<Record<number, string>>({});
  const [severity, setSeverity] = useState<Record<number, string>>({});
  const [proposal, setProposal] = useState(false);
  const [complete, setComplete] = useState(false);
  const [failedExample, setFailedExample] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [terminal, setTerminal] = useState('');
  const [trace, setTrace] = useState<number | null>(null);
  const [runView, setRunView] = useState<RunView>(emptyView());
  const [baselineScore, setBaselineScore] = useState<number | null>(null);
  const [revisedScore, setRevisedScore] = useState<number | null>(null);
  const [statusMessage, setStatusMessage] = useState('');
  const dialog = useRef<HTMLDialogElement>(null);

  const live = isHttpMode && Boolean(runView.runId);
  const rules: UiRule[] = live ? runView.rules : mockRules;
  const findings: UiFinding[] = live ? runView.findings : mockFindings;
  const scenarios: UiScenario[] = live ? runView.scenarios : mockScenarios;
  const policyLabel = live ? `${runView.policyId}-r${runView.revision}` : 'SAMPLE-v1';
  const suiteLabel = live ? runView.suiteId : 'DEMO-SUITE-15';

  useEffect(() => {
    if (trace !== null) dialog.current?.showModal();
    else dialog.current?.close();
  }, [trace]);

  // Mock-mode illustrative progress timer
  useEffect(() => {
    if (!busy || isHttpMode) return;
    const timer = window.setTimeout(() => {
      if (progress < 6) setProgress(progress + 1);
      else {
        setBusy(false);
        if (reached === 3) setComplete(true);
      }
    }, 120);
    return () => window.clearTimeout(timer);
  }, [busy, progress, reached]);

  const navigate = (n: number) => {
    setStep(n);
    setError('');
  };

  const runMock = () => {
    setBusy(true);
    setProgress(0);
    setReached(1);
    setStep(1);
  };

  const runLive = async () => {
    setBusy(true);
    setProgress(0);
    setReached(1);
    setStep(1);
    setStatusMessage('Preparing scenario review…');
    if (context.simulate && runView.runId) {
      setSimulationState('running');
      try {
        const rehearsed = await rehearseRun(runView.runId, true);
        const mapped = mapRunToView(rehearsed);
        setRunView(mapped);
        setBaselineScore(mapped.score);
        setSimulationState(mapped.swarmUsed ? 'completed' : 'failed');
        setStatusMessage(mapped.swarmUsed ? 'Swarm rehearsal complete' : 'Swarm unavailable — using fuzz results');
      } catch {
        setSimulationState('failed');
        setStatusMessage('Swarm rehearsal failed — using fuzz evaluation results');
      }
    } else {
      setSimulationState(context.simulate ? 'not_run' : 'completed');
    }
    setBusy(false);
    setProgress(6);
  };

  const reset = () => {
    setContext(defaultContext);
    setSimulationState('completed');
    setStep(0);
    setReached(0);
    setReview(false);
    setText('');
    setAck(false);
    setConfirmed(false);
    setIntents(initialIntents);
    setDecisions({});
    setSeverity({});
    setProposal(false);
    setComplete(false);
    setFailedExample(false);
    setDeleting(false);
    setBusy(false);
    setTerminal('');
    setError('');
    setTrace(null);
    setRunView(emptyView());
    setBaselineScore(null);
    setRevisedScore(null);
    setStatusMessage('');
  };

  const acceptReady =
    findings.length > 0 &&
    findings.every(
      (_, i) => decisions[i] && decisions[i] !== 'clarify' && (decisions[i] !== 'accept' || i === 0 || severity[i]),
    );
  const accepted = findings.map((_, i) => i).filter((i) => decisions[i] === 'accept');

  const loadSamplePreview = () => {
    setText(policyText);
    setTitle('APAC Travel & Expense Policy');
    setReview(true);
    setConfirmed(false);
    setError('');
    setRunView(emptyView());
  };

  const analyzeWithEngine = async (policyBody: string, policyTitle: string) => {
    setBusy(true);
    setError('');
    setStatusMessage('Calling engine: ingest → extract → fuzz → score…');
    try {
      const seedText = buildSeedText({ goals: context.goals, assumptions: context.assumptions });
      const segments = context.groups
        .filter((g) => g.name.trim())
        .map((g, i) => ({
          id: g.name.trim().toLowerCase().replace(/\s+/g, '_') || `group_${i + 1}`,
          label: g.name.trim(),
          weight: 1,
          attributes: { context: g.context, relationship: g.relationship },
        }));
      let record = await createRun({
        policyText: policyBody,
        title: policyTitle,
        seedText,
        populationSize: Math.min(50, Math.max(5, segments.length * 5 || 15)),
        groups: segments.map((s) => s.id),
        segments,
        locale: 'any',
      });
      if (record.status === 'failed') {
        throw new Error(record.error || record.message || 'Engine run failed');
      }
      const mapped = mapRunToView(record);
      setRunView(mapped);
      setBaselineScore(mapped.score);
      setRevisedScore(null);
      setTitle(mapped.policyTitle || policyTitle);
      setIntents(
        mapped.recommendedActions.length
          ? mapped.recommendedActions.slice(0, 5)
          : mapped.openQuestions.slice(0, 5).length
            ? mapped.openQuestions.slice(0, 5)
            : initialIntents,
      );
      setReview(true);
      setConfirmed(false);
      setStatusMessage(`Engine run ${mapped.runId} · score ${mapped.score ?? 'n/a'}`);
      setSimulationState(context.simulate ? 'not_run' : 'completed');
    } catch (err) {
      const message =
        err instanceof EngineApiError
          ? `Engine error (${err.status}): ${err.body.slice(0, 240)}`
          : err instanceof Error
            ? err.message
            : 'Failed to reach the engine';
      setError(
        `${message}. Is the engine running on :8000? Start it with: uvicorn app.main:app --host 127.0.0.1 --port 8000`,
      );
      setReview(false);
    } finally {
      setBusy(false);
    }
  };

  const onAnalyze = async () => {
    if (!text.trim() || text.length > 50000) {
      setError('Enter between 1 and 50,000 characters.');
      return;
    }
    if (!ack) {
      setError('Confirm that your policy is synthetic or non-confidential.');
      return;
    }
    if (isHttpMode) {
      await analyzeWithEngine(text, title || 'Untitled policy');
      return;
    }
    if (text === policyText) {
      loadSamplePreview();
      return;
    }
    setError('Backend connection needed to analyze custom policy text. Use the sample to explore the interface.');
  };

  const onConfirmContract = () => {
    if (isHttpMode) void runLive();
    else runMock();
  };

  const onConfirmRevision = async () => {
    if (!isHttpMode || !runView.runId) {
      setReached(3);
      setStep(3);
      setBusy(true);
      setProgress(0);
      return;
    }
    setReached(3);
    setStep(3);
    setBusy(true);
    setComplete(false);
    setStatusMessage('Revising policy with the engine…');
    try {
      const instruction = buildRevisionInstruction(findings, accepted, intents);
      const revised = await reviseRun(runView.runId, instruction);
      const mapped = mapRunToView(revised);
      setRevisedScore(mapped.score);
      setRunView(mapped);
      setStatusMessage(`Revised · score ${baselineScore ?? 'n/a'} → ${mapped.score ?? 'n/a'}`);
      setComplete(true);
    } catch (err) {
      const message =
        err instanceof EngineApiError
          ? `Revision failed (${err.status}): ${err.body.slice(0, 240)}`
          : err instanceof Error
            ? err.message
            : 'Revision failed';
      setError(message);
      setComplete(true);
    } finally {
      setBusy(false);
    }
  };

  const exportPreview = () => {
    const blob = new Blob(
      [
        JSON.stringify(
          {
            label: isHttpMode
              ? 'ENGINE RUN EXPORT — NOT AUTHORITATIVE PUBLICATION EVIDENCE'
              : 'ILLUSTRATIVE UI PREVIEW — NOT EVALUATION EVIDENCE',
            mode: isHttpMode ? 'http' : 'mock',
            policy: policyLabel,
            suite: suiteLabel,
            run_id: runView.runId || null,
            baseline_score: baselineScore,
            revised_score: revisedScore,
            accepted_findings: accepted.map((i) => findings[i]?.title).filter(Boolean),
            comparison: failedExample ? 'failed-example' : 'sample-success',
            owner_context: context,
            simulation_status: context.simulate ? simulationState : 'skipped',
            justification: runView.justification || null,
          },
          null,
          2,
        ),
      ],
      { type: 'application/json' },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = isHttpMode ? 'policyfuzz-engine-run.json' : 'policyfuzz-ui-preview.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  const selectedFinding = findings[selected];
  const scoreImproved =
    baselineScore != null && revisedScore != null ? revisedScore >= baselineScore : !failedExample;

  return (
    <>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <header>
        <div className="topbar">
          <div className="brand">
            <span className="logo">
              P<span>×</span>
            </span>
            <h1>PolicyFuzz</h1>
            <Badge>{isHttpMode ? 'ENGINE ADAPTER' : 'SYNTHETIC SAMPLE'}</Badge>
            <Badge tone={isHttpMode ? 'success' : 'warning'}>
              {isHttpMode ? (
                <>
                  <FlaskConical size={12} /> Live engine · temporary FE→engine wiring
                </>
              ) : (
                <>
                  <LockKeyhole size={12} /> Mock preview — illustrative results
                </>
              )}
            </Badge>
          </div>
          <div className="header-meta">
            <FileText size={15} />
            <span>{title || 'Untitled policy'}</span>
            <span className="divider" />
            <code>{live ? runView.runId : 'DEMO-001'}</code>
          </div>
          <div className="session">
            <span>Finance Ops workspace</span>
            <small>{isHttpMode ? 'Engine-connected session' : 'Local design preview'}</small>
          </div>
          <button className="danger subtle" onClick={() => setDeleting(!deleting)}>
            <Trash2 size={15} />
            Delete run
          </button>
          <span className="avatar">FO</span>
        </div>
        <div className="navrow">
          <nav aria-label="Workflow">
            {steps.map((s, i) => (
              <button
                key={s}
                disabled={i > reached}
                aria-current={step === i ? 'step' : undefined}
                onClick={() => navigate(i)}
              >
                <span className="stepnum">{i < step ? <Check size={12} /> : i + 1}</span>
                {s}
              </button>
            ))}
          </nav>
          <span className="engine">
            <i />
            {isHttpMode ? 'Engine connected · /v1 via Vite proxy' : 'Interface preview · API pending'}
          </span>
        </div>
      </header>
      {deleting && (
        <div className="deletebar" role="alert">
          <span>Delete this {isHttpMode ? 'run' : 'preview'} and clear the policy text?</span>
          <button className="danger" onClick={reset}>
            Confirm deletion
          </button>
          <button onClick={() => setDeleting(false)}>Cancel</button>
        </div>
      )}
      <main id="main">
        <div className="page-title">
          <div>
            <div className="eyebrow">
              <span>WORKSPACE / 0{step + 1}</span> ·{' '}
              {['Policy interpretation', 'Scenario inspection', 'Owner review', 'Regression comparison'][step]}
            </div>
            <h2>
              {
                [
                  'Policy setup, goals & interpretation',
                  'Scenarios, behavior & action evidence',
                  'Find the gap. Review the change.',
                  'Before and after: same frozen test suite',
                ][step]
              }
            </h2>
            <p className="muted">
              {
                [
                  'Define published policy, owner goals, affected groups, and assumptions before reviewing the interpretation.',
                  'Explore plausible responses, optional discussion, and conditional consequences.',
                  'Review each finding before confirming a structured revision.',
                  'See what improved, what remains, and whether protected cases still pass.',
                ][step]
              }
            </p>
          </div>
          {step === 0 && (
            <div className="segmented">
              <button className={!review ? 'active' : ''} disabled={reached > 0} onClick={() => setReview(false)}>
                <FileText size={14} />
                Policy submission
              </button>
              <button
                className={review ? 'active' : ''}
                disabled={!text || reached > 0}
                onClick={() => {
                  if (isHttpMode && runView.runId) setReview(true);
                  else if (text === policyText) setReview(true);
                  else setError('Backend connection needed to extract rules from custom policy text.');
                }}
              >
                <Layers size={14} />
                Contract & intent
              </button>
            </div>
          )}
        </div>
        <div className="contextbar">
          <span>
            <ShieldCheck size={14} /> {title || 'Untitled policy'}
          </span>
          <span>{isHttpMode ? 'Engine rehearsal' : 'SGD · Synthetic T&E'}</span>
          <span className="push">
            {reached > 0
              ? `Baseline: ${policyLabel}`
              : isHttpMode
                ? 'Ready to submit to engine'
                : 'No policy submitted to a provider'}
          </span>
        </div>
        <div className="content">
          {error && (
            <div role="alert" className="notice warning">
              <AlertTriangle size={20} />
              <span>{error}</span>
            </div>
          )}
          {statusMessage && isHttpMode && (
            <div className="notice" role="status">
              <Activity size={18} />
              <span>{statusMessage}</span>
            </div>
          )}
          {terminal && (
            <Panel className="terminal">
              <h3>{terminal}</h3>
              <p>No further changes will be applied to this {isHttpMode ? 'run' : 'preview'}.</p>
              <button onClick={reset}>Start a new {isHttpMode ? 'run' : 'preview'}</button>
            </Panel>
          )}

          {!terminal && step === 0 && !review && (
            <div className="input-grid">
              <Panel>
                <div className="section-heading">
                  <span className="iconbox">
                    <FileText />
                  </span>
                  <div>
                    <h3>Your policy, ready for review</h3>
                    <p className="muted small">
                      {isHttpMode
                        ? 'Paste policy text. Analyze sends it to the local engine sidecar.'
                        : 'Paste English travel-and-expense text or explore the sample.'}
                    </p>
                  </div>
                </div>
                <label className="field">
                  Policy title
                  <input value={title} onChange={(e) => setTitle(e.target.value)} />
                </label>
                <label className="field">
                  Policy text
                  <textarea
                    rows={13}
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    placeholder={'Section 4.1 — Meals and receipts\nPaste your policy here…'}
                  />
                </label>
                <div className="row small muted">
                  <span>Plain text · PDF support is not available in this UI</span>
                  <span>{text.length.toLocaleString()} / 50,000 characters</span>
                </div>
                <div className="inset disclosure">
                  <ShieldCheck size={18} />
                  <p>
                    {isHttpMode
                      ? 'Policy text is sent to the local engine (and optional LLM if configured there). Keep content synthetic or non-confidential.'
                      : 'When connected, policy text will be sent to the configured hosted AI provider. This preview stays in your browser and supports the bundled sample only.'}
                  </p>
                </div>
                <label className="checkbox">
                  <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
                  This policy is synthetic or non-confidential.
                </label>
                <div className="actions">
                  <button
                    onClick={() => {
                      setText('');
                      setError('');
                    }}
                  >
                    Clear text
                  </button>
                  <button className="primary" disabled={busy} onClick={() => void onAnalyze()}>
                    {busy ? 'Analyzing…' : 'Analyze policy'}
                    <ArrowRight size={16} />
                  </button>
                </div>
              </Panel>
              <aside>
                <Panel className="sample-card">
                  <span className="iconbox large">
                    <FlaskConical size={27} />
                  </span>
                  <span className="eyebrow">EXPLORE THE WORKFLOW</span>
                  <h3>
                    A small policy.
                    <br />
                    Three revealing edge cases.
                  </h3>
                  <p>See how threshold gaps, overlapping approval rules, and split claims become inspectable findings.</p>
                  <ul className="sample-list">
                    <li>
                      <Check size={16} />
                      Synthetic Singapore T&E policy
                    </li>
                    <li>
                      <Check size={16} />
                      {isHttpMode ? 'Live engine extraction & fuzz' : '15 illustrative test scenarios'}
                    </li>
                    <li>
                      <Check size={16} />
                      Revision and comparison {isHttpMode ? 'via /revise' : 'preview'}
                    </li>
                  </ul>
                  <button
                    className="primary wide"
                    disabled={busy}
                    onClick={() => {
                      setText(policyText);
                      setTitle('APAC Travel & Expense Policy');
                      setAck(true);
                      setError('');
                      if (isHttpMode) void analyzeWithEngine(policyText, 'APAC Travel & Expense Policy');
                      else loadSamplePreview();
                    }}
                  >
                    Use sample policy
                    <ArrowRight size={16} />
                  </button>
                  <small>
                    {isHttpMode
                      ? 'Sample text is sent to the engine like any other policy.'
                      : 'Sample data is illustrative, not benchmark evidence.'}
                  </small>
                </Panel>
                <Panel>
                  <span className="eyebrow">HOW IT WORKS</span>
                  {['Confirm the interpretation', 'Inspect test evidence', 'Review a proposed revision', 'Compare the same test suite'].map(
                    (s, i) => (
                      <div className="how" key={s}>
                        <span className="stepnum">{i + 1}</span>
                        {s}
                      </div>
                    ),
                  )}
                </Panel>
              </aside>
            </div>
          )}

          {!terminal && step === 0 && (
            <SetupEditor value={context} onChange={(c) => { setContext(c); setConfirmed(false); }} locked={reached > 0} />
          )}

          {!terminal && step === 0 && review && (
            <>
              <Panel className="row summary">
                <div className="section-heading">
                  <span className="iconbox">
                    <ShieldCheck />
                  </span>
                  <div>
                    <span className="eyebrow">
                      {live ? 'ENGINE INTERPRETATION' : 'SAMPLE INTERPRETATION · NOT LIVE EXTRACTION'}
                    </span>
                    <h3>Policy interpretation ready for review</h3>
                    <p className="small">
                      {rules.length} rules
                      {live && runView.openQuestions.length ? `, ${runView.openQuestions.length} open questions` : ''}
                      {live && runView.conflicts.length ? `, ${runView.conflicts.length} conflicts` : ''}
                      {!live ? `, 1 unsupported clause, and ${intents.length} proposed intent rules` : `, ${intents.length} intent / action hints`}
                      .
                    </p>
                  </div>
                </div>
                <button disabled={reached > 0 || busy} onClick={() => setReview(false)}>
                  Edit source text
                </button>
              </Panel>
              {(live ? runView.openQuestions : ['“Reasonable incidental expenses” has not been converted into a numerical rule.']).map(
                (q) => (
                  <div className="notice warning" key={q}>
                    <AlertTriangle />
                    <div>
                      <strong>{live ? 'Open question' : 'Unsupported clause · Section 4.3'}</strong>
                      <p>{live ? q : '“Reasonable incidental expenses” has not been converted into a numerical rule. Affected outcomes may be inconclusive.'}</p>
                    </div>
                  </div>
                ),
              )}
              <div className="review-grid">
                <div>
                  <Panel className="row">
                    <div>
                      <h3>Extracted structural rules</h3>
                      <span className="small muted">Source wording remains separate from intended behavior.</span>
                    </div>
                    <button onClick={() => setExpanded(!expanded)}>
                      {expanded ? 'Show key rules' : `Show all ${rules.length} rules`}
                    </button>
                  </Panel>
                  <div className="rule-stack">
                    {rules.slice(0, expanded ? rules.length : Math.min(5, rules.length)).map((r) => (
                      <Panel key={r.id}>
                        <div className="row">
                          <h4>
                            <Badge>{r.id}</Badge> {r.title}
                          </h4>
                          <code>§ {r.section}</code>
                        </div>
                        <div className="logic">
                          <div>
                            <span className="eyebrow">CONDITION</span>
                            <code>{r.condition}</code>
                          </div>
                          <div>
                            <span className="eyebrow">EFFECT</span>
                            <code className="teal">{r.effect}</code>
                          </div>
                        </div>
                        <blockquote>“{r.quote}”</blockquote>
                        <details>
                          <summary>
                            <Code2 size={14} />
                            Inspect structured rule
                          </summary>
                          <pre>{JSON.stringify({ id: r.id, condition: r.condition, effect: r.effect, source_section: r.section }, null, 2)}</pre>
                        </details>
                      </Panel>
                    ))}
                    {!rules.length && (
                      <Panel>
                        <p className="muted">No rules were extracted. Try enabling an LLM key on the engine, or paste a clearer policy.</p>
                      </Panel>
                    )}
                  </div>
                </div>
                <aside>
                  <Panel>
                    <span className="eyebrow">
                      OWNER REVIEW <Badge tone="warning">{intents.length} intent rules</Badge>
                    </span>
                    <h3>Owner intended behavior</h3>
                    <p className="muted small">Confirm the constraints that describe what the policy should enforce.</p>
                    {intents.map((t, i) => (
                      <div className="intent" key={i}>
                        <div className="row">
                          <code>INT-{String(i + 1).padStart(2, '0')}</code>
                          <span className="small teal">Proposed intent</span>
                        </div>
                        <textarea
                          aria-label={`Intent rule ${i + 1}`}
                          value={t}
                          readOnly={reached > 0}
                          onChange={(e) => {
                            setIntents(intents.map((v, n) => (n === i ? e.target.value : v)));
                            setConfirmed(false);
                          }}
                          rows={4}
                        />
                        {i > 2 && reached === 0 && (
                          <button className="text-button" onClick={() => setIntents(intents.filter((_, n) => n !== i))}>
                            Remove intent rule
                          </button>
                        )}
                      </div>
                    ))}
                    <button
                      className="wide"
                      disabled={intents.length >= 5 || reached > 0}
                      onClick={() => {
                        setIntents([...intents, '']);
                        setConfirmed(false);
                      }}
                    >
                      <Plus size={16} />
                      Add intent rule
                    </button>
                  </Panel>
                  <Panel>
                    <span className="eyebrow">REVIEW CHECKLIST</span>
                    <p className="checkline">
                      <Check />
                      Source quotations visible
                    </p>
                    <p className="checkline">
                      <Check />
                      Unsupported wording retained
                    </p>
                    <p className="checkline">
                      <AlertTriangle />
                      Owner confirmation required
                    </p>
                  </Panel>
                </aside>
              </div>
              <Panel className="approval row">
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={confirmed}
                    disabled={reached > 0}
                    onChange={(e) => setConfirmed(e.target.checked)}
                  />
                  I confirm the extracted rules and {intents.length} intent rules represent the intended baseline.
                </label>
                <div className="actions">
                  <button
                    className="danger subtle"
                    disabled={reached > 0}
                    onClick={() => setTerminal('Policy interpretation rejected')}
                  >
                    Reject interpretation
                  </button>
                  <button
                    className="primary"
                    disabled={!confirmed || !setupValid(context) || intents.some((t) => !t.trim()) || reached > 0 || busy}
                    onClick={onConfirmContract}
                  >
                    Confirm contract & {isHttpMode ? 'review results' : 'launch preview'}
                    <ArrowRight size={16} />
                  </button>
                </div>
              </Panel>
            </>
          )}

          {!terminal && step === 1 && (
            <>
              <Panel>
                <div className="row">
                  <h3>
                    <FlaskConical size={18} />
                    Bounded testing cycle
                  </h3>
                  <Badge tone={busy ? 'warning' : 'success'}>
                    {busy ? (isHttpMode ? 'Engine working…' : 'Playing illustrative progress') : isHttpMode ? 'Engine baseline ready' : 'Sample baseline complete'}
                  </Badge>
                </div>
                <div className="pipeline">
                  {stages.map((s, i) => (
                    <div className={i === 4 ? 'targeted' : ''} key={s}>
                      <div className="row">
                        <code>0{i + 1}</code>
                        {!busy || i < progress ? (
                          <CircleCheck size={16} />
                        ) : i === progress ? (
                          <Activity size={16} />
                        ) : (
                          <span>○</span>
                        )}
                      </div>
                      <strong>{s}</strong>
                      <small>
                        {busy && i > progress
                          ? 'Pending'
                          : isHttpMode
                            ? i === 5
                              ? `${scenarios.length} scenarios`
                              : 'Engine stage'
                            : i === 4
                              ? 'One targeted batch'
                              : i === 5
                                ? '15 scenarios'
                                : 'Sample stage'}
                      </small>
                    </div>
                  ))}
                </div>
                {!isHttpMode && (
                  <div className="inset small">
                    <AlertTriangle size={16} /> Illustrative adaptation: initial coverage misses an intent rule; one
                    targeted batch fills the gap before suite freeze.
                  </div>
                )}
              </Panel>
              {busy ? (
                <Panel>
                  <p role="status">{isHttpMode ? statusMessage || 'Working with the engine…' : `${stages[progress]}…`}</p>
                  <div className="loading" />
                </Panel>
              ) : (
                <>
                  {findings[0] && (
                    <BehaviorEvidence
                      index={0}
                      context={context}
                      state={simulationState}
                      onState={setSimulationState}
                      finding={findings[0]}
                      policyLabel={policyLabel}
                      live={live}
                    />
                  )}
                  <div className="metrics">
                    <Metric
                      label="RULE COVERAGE"
                      value={`${live ? runView.ruleCount : 8}/${live ? runView.ruleCount : 8}`}
                      detail={live ? 'Rules in compiled IR' : 'Rules exercised · illustrative sample'}
                    />
                    <Metric
                      label="INTENT COVERAGE"
                      value={`${intents.length}/${intents.length}`}
                      detail={live ? 'Owner intent / revision hints' : 'Original sample intent rules exercised'}
                    />
                    <Metric
                      label="FROZEN SCENARIOS"
                      value={String(scenarios.length)}
                      detail={live ? 'Engine scenario suite' : 'Normal, boundary, and adversarial'}
                    />
                    <Metric
                      label={live ? 'EFFECTIVENESS SCORE' : 'REVIEWABLE FINDINGS'}
                      value={live ? String(runView.score ?? '—') : String(findings.length)}
                      detail={
                        live
                          ? `${runView.failCount} non-pass · ${runView.passCount} pass`
                          : 'One intent breach, gap, and conflict'
                      }
                    />
                  </div>
                  {!live &&
                    (intents.length !== 3 || intents.some((t, i) => t !== initialIntents[i])) && (
                      <div className="notice warning">
                        Edited intent is retained for UI review only. These illustrative results belong to the original
                        sample intent and do not evaluate your edits.
                      </div>
                    )}
                  <Panel>
                    <div className="row">
                      <h3>Response scenarios & action evaluation</h3>
                      <Badge>{suiteLabel}</Badge>
                    </div>
                    <div className="filters" role="group" aria-label="Scenario filters">
                      {['All', 'Normal', 'Boundary', 'Adversarial', 'Failed'].map((f) => (
                        <button className={filter === f ? 'active' : ''} onClick={() => setFilter(f)} key={f}>
                          {f}
                          {f === 'All' ? ` scenarios (${scenarios.length})` : ''}
                        </button>
                      ))}
                    </div>
                    <div className="inset small">
                      <ShieldCheck size={17} /> A policy outcome and a test assertion are different: “Allowed” does not
                      mean “Passed”.
                    </div>
                    <div className="table-scroll" tabIndex={0} role="region" aria-label="Scenario results">
                      <table>
                        <thead>
                          <tr>
                            <th>Scenario</th>
                            <th>Affected group / context & proposed action</th>
                            <th>Category</th>
                            <th>Policy outcome</th>
                            <th>Assertion</th>
                            <th>Evidence</th>
                          </tr>
                        </thead>
                        <tbody>
                          {scenarios
                            .filter(
                              (s) =>
                                filter === 'All' ||
                                s.category === filter ||
                                (filter === 'Failed' && s.assertion === 'Failed'),
                            )
                            .map((s) => (
                              <tr key={s.id}>
                                <td>
                                  <code>{s.id}</code>
                                </td>
                                <td>
                                  <span className="badge">
                                    {live
                                      ? context.groups[0]?.name || 'Audience'
                                      : s.finding === 2
                                        ? 'Employee · manager'
                                        : 'Employee · Finance reviewer'}
                                  </span>
                                  <p>{s.facts}</p>
                                  <small>
                                    {s.finding === null
                                      ? 'Proposed action: submit the described claim.'
                                      : live
                                        ? `Linked finding: ${findings[s.finding]?.title || s.id}`
                                        : s.finding === 0
                                          ? 'Proposed action: submit the second claim separately.'
                                          : s.finding === 1
                                            ? 'Proposed action: submit at the exact receipt threshold.'
                                            : 'Proposed action: submit the hotel claim under the exception.'}
                                  </small>
                                </td>
                                <td>
                                  <Badge>{s.category}</Badge>
                                </td>
                                <td>{s.outcome}</td>
                                <td>
                                  <Badge tone={s.assertion === 'Failed' ? 'danger' : 'success'}>{s.assertion}</Badge>
                                </td>
                                <td>
                                  {s.finding !== null ? (
                                    <button className="text-button" onClick={() => setTrace(s.finding)}>
                                      Inspect
                                      <ChevronRight size={14} />
                                    </button>
                                  ) : (
                                    <span className="small muted">Summary only</span>
                                  )}
                                </td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                    </div>
                    <details className="inset">
                      <summary>Unsupported clause disposition</summary>
                      <p>
                        {live
                          ? runView.openQuestions.join(' ') ||
                            'No open questions were reported by the engine for this run.'
                          : 'Section 4.3 is retained as an unsupported-clause candidate. No numeric incidental limit is invented. Full dimension traces require the backend.'}
                      </p>
                    </details>
                    <div className="actions">
                      <span className="muted small">
                        {live ? 'Live engine results' : 'Illustrative results · no evaluation engine connected'}
                      </span>
                      <button
                        className="primary"
                        disabled={!findings.length}
                        onClick={() => {
                          setReached(Math.max(reached, 2));
                          setStep(2);
                          setSelected(0);
                        }}
                      >
                        Review findings
                        <ArrowRight size={16} />
                      </button>
                    </div>
                  </Panel>
                </>
              )}
            </>
          )}

          {!terminal && step === 2 && selectedFinding && (
            <>
              <Panel className="row">
                <div>
                  <span className="eyebrow">STAGE 03 / OWNER DECISIONS</span>
                  <h3>Findings & structured revision</h3>
                  <p className="muted small">
                    {Object.keys(decisions).length}/{findings.length} findings reviewed · {accepted.length} accepted
                  </p>
                </div>
                <Badge tone="warning">{proposal ? 'Proposal awaiting confirmation' : 'Review each finding'}</Badge>
              </Panel>
              <div className="findings-grid">
                <aside>
                  {findings.map((f, i) => (
                    <button
                      aria-label={`Select finding ${i + 1}`}
                      className={`finding-card ${selected === i ? 'selected' : ''}`}
                      onClick={() => setSelected(i)}
                      key={`${f.scenario}-${i}`}
                    >
                      <div className="row">
                        <code>FND-{String(i + 1).padStart(3, '0')}</code>
                        {decisions[i] && (
                          <Badge tone={decisions[i] === 'accept' ? 'success' : 'neutral'}>
                            {decisions[i] === 'accept'
                              ? 'Accepted'
                              : decisions[i] === 'clarify'
                                ? 'Needs clarification'
                                : 'Rejected'}
                          </Badge>
                        )}
                      </div>
                      <h4>{f.title}</h4>
                      <div className="badge-row">
                        <Badge tone="danger">{f.type}</Badge>
                        <Badge>{f.level}</Badge>
                      </div>
                      <p>{f.facts}</p>
                      <span className="teal small">Inspect evidence →</span>
                    </button>
                  ))}
                  {!live && (
                    <>
                      <Panel className="candidate">
                        <Badge tone="warning">Assumption requiring validation</Badge>
                        <h4>Manager response time is unconfirmed</h4>
                        <p className="small">
                          ASM-02 may affect proposed choices. This uncertainty is not a verified policy defect.
                        </p>
                      </Panel>
                      <Panel className="candidate">
                        <Badge>Read-only candidate</Badge>
                        <h4>Incidental expenses need clarification</h4>
                        <p className="small">
                          “Reasonable” has no supported numerical meaning. Visible for owner review; excluded from
                          revision selection.
                        </p>
                      </Panel>
                    </>
                  )}
                </aside>
                <div>
                  <Panel>
                    <div className="row">
                      <span className="eyebrow">ACTIVE FINDING · {selectedFinding.scenario}</span>
                      <Badge tone="danger">{selectedFinding.type}</Badge>
                    </div>
                    <h3>{selectedFinding.title}</h3>
                    <BehaviorEvidence
                      index={selected}
                      context={context}
                      state={simulationState}
                      finding={selectedFinding}
                      policyLabel={policyLabel}
                      live={live}
                    />
                    <Evidence finding={selectedFinding} policyLabel={policyLabel} />
                    {!proposal && (
                      <div className="decision-bar">
                        {selected > 0 && (
                          <label>
                            Reviewer severity
                            <select
                              aria-label="Reviewer severity"
                              value={severity[selected] || ''}
                              onChange={(e) => setSeverity({ ...severity, [selected]: e.target.value })}
                            >
                              <option value="">Select severity</option>
                              <option value="low">Low</option>
                              <option value="medium">Medium</option>
                              <option value="high">High</option>
                              <option value="critical">Critical</option>
                            </select>
                          </label>
                        )}
                        <div className="actions">
                          <button onClick={() => setDecisions({ ...decisions, [selected]: 'clarify' })}>
                            Request clarification
                          </button>
                          <button onClick={() => setDecisions({ ...decisions, [selected]: 'reject' })}>
                            Reject finding
                          </button>
                          <button
                            className="primary"
                            disabled={selected > 0 && !severity[selected]}
                            onClick={() => setDecisions({ ...decisions, [selected]: 'accept' })}
                          >
                            <Check size={16} />
                            Accept finding
                          </button>
                        </div>
                      </div>
                    )}
                  </Panel>
                  {proposal && (
                    <>
                      <Panel>
                        <span className="eyebrow">
                          PROPOSAL {live ? `${runView.runId}-rev` : 'DEMO-REV-01'} · NOT YET TESTED
                        </span>
                        <h3>Proposed structured rule modifications</h3>
                        <p className="muted small">
                          {live
                            ? 'Revision instruction will be sent to POST /v1/runs/{id}/revise.'
                            : 'Illustrative change summaries for your accepted findings. Backend validation is pending.'}
                        </p>
                        {accepted.map((i) => (
                          <div className="diff" key={i}>
                            <h4>{findings[i].title}</h4>
                            <div className="two-col">
                              <div>
                                <span className="eyebrow">ORIGINAL · {policyLabel}</span>
                                <p>
                                  <code>{findings[i].before}</code>
                                </p>
                              </div>
                              <div>
                                <span className="eyebrow">PROPOSED</span>
                                <p>
                                  <code>{findings[i].after}</code>
                                </p>
                              </div>
                            </div>
                          </div>
                        ))}
                      </Panel>
                      <div className="notice warning wording">
                        <AlertTriangle />
                        <div>
                          <strong>Unverified wording suggestion — not what was tested</strong>
                          <p>
                            The structured changes and draft prose are separate.
                            {live ? ' The engine will recompile IR from the revision instruction.' : ' This preview does not validate either.'}
                          </p>
                          {accepted.map((i) => (
                            <blockquote key={i}>“{findings[i].draft}”</blockquote>
                          ))}
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </div>
              <Panel className="approval row">
                <div className="section-heading">
                  <FlaskConical />
                  <p className="small">
                    No automatic publication.
                    <br />
                    <span className="muted">
                      The comparison {live ? 're-runs the engine suite after revision' : 'preview uses the same 15 sample scenarios'}.
                    </span>
                  </p>
                </div>
                {!proposal ? (
                  <button
                    className="primary"
                    disabled={!acceptReady}
                    onClick={() => {
                      if (!accepted.length) setTerminal('Completed without a revision');
                      else setProposal(true);
                    }}
                  >
                    Prepare revision
                    <ArrowRight size={16} />
                  </button>
                ) : (
                  <div className="actions">
                    <button className="danger subtle" onClick={() => setTerminal('Revision rejected')}>
                      Reject revision
                    </button>
                    <button className="primary" disabled={busy} onClick={() => void onConfirmRevision()}>
                      Confirm revision & retest
                      <ArrowRight size={16} />
                    </button>
                  </div>
                )}
              </Panel>
            </>
          )}

          {!terminal && step === 2 && !selectedFinding && (
            <Panel>
              <h3>No reviewable findings</h3>
              <p className="muted">The engine reported no non-passing findings for this run.</p>
              <button onClick={() => setTerminal('Completed without a revision')}>Finish without revision</button>
            </Panel>
          )}

          {!terminal && step === 3 && (
            <>
              {!complete ? (
                <Panel>
                  <h3>Not yet tested</h3>
                  <p role="status">
                    {isHttpMode ? statusMessage || 'Waiting for engine revision…' : 'Playing illustrative retest sequence…'}
                  </p>
                  <div className="loading" />
                </Panel>
              ) : (
                <>
                  <BehavioralComparison
                    context={context}
                    accepted={accepted}
                    onCompatibilityChange={setComparisonCompatible}
                    findingsList={findings}
                    live={live}
                    baselineLabel={live ? `${runView.policyId}-r${(runView.revision || 1) - (revisedScore != null ? 1 : 0)}` : 'SAMPLE-v1'}
                    revisedLabel={policyLabel}
                    suiteLabel={suiteLabel}
                  />
                  {comparisonCompatible && (
                    <>
                      {!live && (
                        <div className="row inset">
                          <span className="eyebrow">UI STATE PREVIEW · ILLUSTRATIVE COMPARISON</span>
                          <div className="segmented">
                            <button className={!failedExample ? 'active' : ''} onClick={() => setFailedExample(false)}>
                              Successful state
                            </button>
                            <button className={failedExample ? 'active' : ''} onClick={() => setFailedExample(true)}>
                              Failed safeguard state
                            </button>
                          </div>
                        </div>
                      )}
                      <Panel className={`result-banner ${!scoreImproved ? 'result-failed' : ''}`}>
                        <span className="iconbox">{!scoreImproved ? <AlertTriangle /> : <ShieldCheck />}</span>
                        <div>
                          <h3>
                            {live
                              ? scoreImproved
                                ? 'Revision completed — effectiveness did not worsen'
                                : 'Revision completed — effectiveness score dropped'
                              : failedExample
                                ? 'Revision did not pass all safeguards'
                                : 'Revision passed all safeguards for this test suite'}
                          </h3>
                          <p>
                            {live
                              ? `Baseline score ${baselineScore ?? 'n/a'} → revised score ${revisedScore ?? 'n/a'}. ${accepted.length} findings targeted in the revision instruction.`
                              : failedExample
                                ? 'One previously passing protected case regressed in this illustrative failure state.'
                                : `${accepted.length} accepted findings resolved in the illustrative comparison. ${3 - accepted.length} findings remain outside the selected revision.`}
                          </p>
                          <Badge tone={!scoreImproved ? 'danger' : 'success'}>
                            {live
                              ? `Score ${baselineScore ?? '—'} → ${revisedScore ?? '—'}`
                              : failedExample
                                ? 'Safeguards failed'
                                : '7 / 7 safeguards passed'}{' '}
                            · {live ? 'Engine results' : 'Sample results'}
                          </Badge>
                        </div>
                      </Panel>
                      {live && runView.justification && (
                        <Panel>
                          <span className="eyebrow">EFFECTIVENESS JUSTIFICATION</span>
                          <p>{runView.justification}</p>
                          {runView.recommendedActions.length > 0 && (
                            <ul>
                              {runView.recommendedActions.map((a) => (
                                <li key={a}>{a}</li>
                              ))}
                            </ul>
                          )}
                        </Panel>
                      )}
                      {!live && (
                        <>
                          <div className="row">
                            <h3>Backend safeguard checklist</h3>
                            <span className="small muted">UI examples; not computed by this frontend</span>
                          </div>
                          <div className="gates">
                            {gates.map((g, i) => {
                              const fail = failedExample && [2, 3, 6].includes(i);
                              return (
                                <Panel key={g}>
                                  <div className="row">
                                    <code>SAFEGUARD 0{i + 1}</code>
                                    <Badge tone={fail ? 'danger' : 'success'}>{fail ? 'Failed' : 'Passed'}</Badge>
                                  </div>
                                  <h4>{g}</h4>
                                  <div className="inset small">
                                    {fail
                                      ? 'Example regression requires owner review.'
                                      : i === 0
                                        ? 'DEMO-SUITE-15 is unchanged.'
                                        : i === 1
                                          ? `${accepted.length}/${accepted.length} targeted findings fixed.`
                                          : 'Illustrative check satisfied.'}
                                  </div>
                                </Panel>
                              );
                            })}
                          </div>
                        </>
                      )}
                      <Panel className="row">
                        <span className="small muted">
                          {live
                            ? 'Engine adapter export — not evidence that a policy is ready to publish.'
                            : 'This is a UI preview, not evidence that a policy is correct or ready to publish.'}
                        </span>
                        <button className="primary" onClick={exportPreview}>
                          <Download size={16} />
                          Export {live ? 'run summary' : 'labelled preview'}
                        </button>
                      </Panel>
                    </>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </main>
      <footer>
        <span>PolicyFuzz · Travel & expense policy QA</span>
        <span>
          <Fingerprint size={14} />
          {isHttpMode ? 'Temporary FE→engine adapter · Person 1 /api/v1 still pending' : 'Synthetic interface preview · Backend integration pending'}
        </span>
      </footer>
      <dialog
        ref={dialog}
        aria-labelledby="trace-title"
        onCancel={() => setTrace(null)}
        onClick={(e) => {
          if (e.target === e.currentTarget) setTrace(null);
        }}
      >
        <div className="drawer-header">
          <div>
            <span className="eyebrow">SCENARIO EVIDENCE</span>
            <h2 id="trace-title">Evidence inspector</h2>
          </div>
          <button aria-label="Close evidence inspector" onClick={() => setTrace(null)}>
            <X />
          </button>
        </div>
        <div className="drawer-content">
          {trace !== null && findings[trace] && (
            <>
              <h3>{findings[trace].title}</h3>
              <BehaviorEvidence
                index={trace}
                context={context}
                state={simulationState}
                finding={findings[trace]}
                policyLabel={policyLabel}
                live={live}
              />
              <Evidence finding={findings[trace]} policyLabel={policyLabel} />
              <div className="inset">
                <span className="eyebrow">TRACE IDENTITY</span>
                <p>
                  <code>
                    {findings[trace].scenario} · {policyLabel}
                  </code>
                </p>
                <p className="small muted">
                  {live ? `Run ${runView.runId}` : 'Full execution hash: unavailable in the illustrative preview.'}
                </p>
              </div>
            </>
          )}
        </div>
        <div className="drawer-footer">
          <button onClick={() => setTrace(null)}>Close inspector</button>
          <button
            className="primary"
            onClick={() => {
              if (trace !== null) setSelected(trace);
              setTrace(null);
              setReached(Math.max(reached, 2));
              setStep(2);
            }}
          >
            Review finding
            <ArrowRight size={16} />
          </button>
        </div>
      </dialog>
    </>
  );
}
