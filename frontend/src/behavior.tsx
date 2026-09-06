import { useEffect, useState } from 'react';
import { Plus, Users, Target, MessageSquare, AlertTriangle } from 'lucide-react';
import { findings as mockFindings } from './preview';
import type { UiFinding } from './api/types';

// Local form state only. Person 1 owns the eventual request and RunView schemas.
export type SetupContext = {
  goals: string[];
  groups: { name: string; context: string; relationship: string }[];
  assumptions: { text: string; source: string; confirmed: boolean }[];
  simulate: boolean;
};
export type SimulationState = 'not_run' | 'running' | 'completed' | 'incomplete' | 'failed';

export const defaultContext: SetupContext = {
  goals: [
    'Keep daily meal reimbursements within SGD 100 while preserving access to necessary meals.',
    'Avoid conflicting approval requirements for international hotels.',
    'Require receipts for claims at or above SGD 50.',
  ],
  groups: [
    {
      name: 'Travelling employees',
      context: 'Employees travelling regionally and submitting meal and lodging claims.',
      relationship: 'Claim submitters',
    },
    {
      name: 'Approving managers',
      context: 'Managers reviewing expense exceptions.',
      relationship: 'Approval decisions',
    },
    {
      name: 'Finance reviewers',
      context: 'Finance operations reviewing claims and supporting evidence.',
      relationship: 'Policy owners and reviewers',
    },
  ],
  assumptions: [
    { text: 'Employees submit claims individually.', source: 'Synthetic submission workflow', confirmed: true },
    {
      text: 'Managers can review exceptions within one working day.',
      source: 'Owner-provided service expectation; validation pending',
      confirmed: false,
    },
  ],
  simulate: false,
};

export function setupValid(c: SetupContext) {
  return (
    c.goals.length > 0 &&
    c.goals.every((x) => x.trim()) &&
    c.groups.length > 0 &&
    c.groups.every((g) => g.name.trim() && g.context.trim() && g.relationship.trim()) &&
    c.assumptions.length > 0 &&
    c.assumptions.every((a) => a.text.trim() && a.source.trim())
  );
}

export function isSampleContext(c: SetupContext) {
  return JSON.stringify({ ...c, simulate: false }) === JSON.stringify(defaultContext);
}

export function SetupEditor({
  value,
  onChange,
  locked,
}: {
  value: SetupContext;
  onChange: (c: SetupContext) => void;
  locked: boolean;
}) {
  return (
    <section className="behavior-setup" aria-label="Goals, groups and assumptions">
      <div className="row">
        <div>
          <span className="eyebrow">POLICY OWNER CONTEXT</span>
          <h3>Goals, affected groups & assumptions</h3>
        </div>
        <span className="badge">{locked ? 'Frozen for this preview' : 'Owner-provided · separate from policy wording'}</span>
      </div>
      <div className="setup-columns">
        <section className="panel">
          <div className="row">
            <h3>
              <Target size={18} />
              B. Owner goals
            </h3>
            <button disabled={locked} onClick={() => onChange({ ...value, goals: [...value.goals, ''] })}>
              <Plus size={14} />
              Add goal
            </button>
          </div>
          {value.goals.map((g, i) => (
            <div className="intent" key={i}>
              <label className="field">
                Goal {i + 1}
                <textarea
                  rows={2}
                  value={g}
                  readOnly={locked}
                  onChange={(e) =>
                    onChange({ ...value, goals: value.goals.map((x, n) => (n === i ? e.target.value : x)) })
                  }
                />
              </label>
              <button
                disabled={locked}
                className="text-button"
                onClick={() => onChange({ ...value, goals: value.goals.filter((_, n) => n !== i) })}
              >
                Remove goal {i + 1}
              </button>
            </div>
          ))}
        </section>
        <section className="panel">
          <div className="row">
            <h3>
              <Users size={18} />
              C. Affected groups
            </h3>
            <button
              disabled={locked}
              onClick={() =>
                onChange({ ...value, groups: [...value.groups, { name: '', context: '', relationship: '' }] })
              }
            >
              Add affected group
            </button>
          </div>
          {value.groups.map((g, i) => (
            <div className="intent" key={i}>
              {(['name', 'context', 'relationship'] as const).map((k) => (
                <label className="field" key={k}>
                  {k === 'name' ? 'Group name' : k === 'context' ? 'Operational context' : 'Relationship to policy'}{' '}
                  {i + 1}
                  <input
                    value={g[k]}
                    readOnly={locked}
                    onChange={(e) =>
                      onChange({
                        ...value,
                        groups: value.groups.map((x, n) => (n === i ? { ...x, [k]: e.target.value } : x)),
                      })
                    }
                  />
                </label>
              ))}
              <button
                className="text-button"
                disabled={locked}
                onClick={() => onChange({ ...value, groups: value.groups.filter((_, n) => n !== i) })}
              >
                Remove group {i + 1}
              </button>
            </div>
          ))}
        </section>
        <section className="panel">
          <div className="row">
            <h3>D. Assumptions</h3>
            <button
              disabled={locked}
              onClick={() =>
                onChange({ ...value, assumptions: [...value.assumptions, { text: '', source: '', confirmed: false }] })
              }
            >
              Add assumption
            </button>
          </div>
          {value.assumptions.map((a, i) => (
            <div className="intent" key={i}>
              <span className={`badge ${a.confirmed ? 'success' : 'warning'}`}>
                {a.confirmed ? 'Owner confirmed' : 'Unconfirmed assumption'}
              </span>
              <label className="field">
                Assumption {i + 1}
                <textarea
                  value={a.text}
                  rows={2}
                  readOnly={locked}
                  onChange={(e) =>
                    onChange({
                      ...value,
                      assumptions: value.assumptions.map((x, n) =>
                        n === i ? { ...x, text: e.target.value, confirmed: false } : x,
                      ),
                    })
                  }
                />
              </label>
              <label className="field">
                Source or rationale {i + 1}
                <input
                  value={a.source}
                  readOnly={locked}
                  onChange={(e) =>
                    onChange({
                      ...value,
                      assumptions: value.assumptions.map((x, n) =>
                        n === i ? { ...x, source: e.target.value, confirmed: false } : x,
                      ),
                    })
                  }
                />
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={a.confirmed}
                  disabled={locked}
                  onChange={(e) =>
                    onChange({
                      ...value,
                      assumptions: value.assumptions.map((x, n) =>
                        n === i ? { ...x, confirmed: e.target.checked } : x,
                      ),
                    })
                  }
                />
                Confirm assumption {i + 1}
              </label>
              <button
                className="text-button"
                disabled={locked}
                onClick={() => onChange({ ...value, assumptions: value.assumptions.filter((_, n) => n !== i) })}
              >
                Remove assumption {i + 1}
              </button>
            </div>
          ))}
        </section>
        <section className="panel simulation-setting">
          <MessageSquare size={23} />
          <h3>Optional interaction simulation</h3>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={value.simulate}
              disabled={locked}
              onChange={(e) => onChange({ ...value, simulate: e.target.checked })}
            />
            Explore interactions between affected groups
          </label>
          <p className="small muted">
            Explore how discussion might influence proposed choices. Simulated responses are behavioral hypotheses, not
            predictions of what people will actually do.
          </p>
          <span className="badge">{value.simulate ? 'Enabled for preview' : 'Off · direct action evaluation'}</span>
        </section>
      </div>
      {!setupValid(value) && (
        <div className="notice warning" role="alert">
          Add at least one complete goal, affected group, and sourced assumption before confirming.
        </div>
      )}
    </section>
  );
}

const choices = [
  [
    'Submit the second meal claim separately because the published rule describes an individual cap.',
    'Bundle the claims and request clarification before submitting.',
    'If both claims are reimbursed: SGD 60 + SGD 50 = SGD 110; SGD 110 − SGD 100 = SGD 10 above the goal.',
    'Both claims must actually be reimbursed for this excess to occur. Eligibility alone does not establish reimbursement.',
  ],
  [
    'Submit the SGD 50 claim without a receipt, interpreting “above SGD 50” literally.',
    'Attach a receipt voluntarily at the threshold.',
    'At SGD 50: (50 < 50) is false and (50 > 50) is false. Neither receipt rule applies.',
    'No receipt-compliance percentage or monetary loss can be inferred from this gap.',
  ],
  [
    'Submit the international hotel claim without approval, relying on the low-value exception.',
    'Ask a manager to resolve the competing requirements first.',
    'SGD 220 < SGD 250. Both hotel rules apply and yield different approval values.',
    'Delay and business cost are unknown; no time or cost estimate is calculated.',
  ],
];

function choiceFor(index: number, finding?: UiFinding) {
  if (choices[index]) return choices[index];
  if (!finding) {
    return [
      'Review the scenario facts.',
      'Request clarification.',
      '—',
      'Live engine result; no illustrative formula.',
    ];
  }
  return [
    finding.facts,
    finding.after || 'Revise the policy based on this finding.',
    finding.observed,
    'Derived from engine evaluation traces; not an illustrative formula.',
  ];
}

export function BehaviorEvidence({
  index,
  context,
  state,
  onState,
  finding,
  policyLabel = 'SAMPLE-v1',
  live = false,
}: {
  index: number;
  context: SetupContext;
  state: SimulationState;
  onState?: (s: SimulationState) => void;
  finding?: UiFinding;
  policyLabel?: string;
  live?: boolean;
}) {
  const f = finding || mockFindings[index];
  if (!f) return null;
  const c = choiceFor(index, finding);
  const goal = context.goals[Math.min(index, context.goals.length - 1)] || context.goals[0] || '—';
  return (
    <section className="behavior-evidence">
      <div className="inset">
        <span className="eyebrow">
          SCENARIO CONTEXT · {f.scenario} · {policyLabel}
        </span>
        <div className="two-col">
          <p>
            <strong>Affected roles</strong>
            <br />
            {context.groups.map((g) => g.name).filter(Boolean).slice(0, 2).join(' · ') || 'Owner-defined groups'}
          </p>
          <p>
            <strong>Linked goal</strong>
            <br />
            G-{String(Math.min(index, context.goals.length - 1) + 1).padStart(2, '0')} · {goal}
          </p>
        </div>
        <p className="small">
          {context.assumptions
            .slice(0, 2)
            .map((a, i) => `ASM-${String(i + 1).padStart(2, '0')}: ${a.text}`)
            .join(' ')}
        </p>
        {!live && !isSampleContext(context) && (
          <p className="notice warning">
            Your setup differs from this sample. These examples do not evaluate the edited groups, goals, or assumptions.
          </p>
        )}
      </div>
      <div className="two-col">
        <div className="hypothesis">
          <span className="badge warning">Behavioral hypothesis</span>
          <h4>People might respond this way</h4>
          <p>{c[0]}</p>
          <p className="small">
            <strong>Alternative choice:</strong> {c[1]}
          </p>
          <small>Depends on interpretation and submission workflow. No probability is assigned.</small>
        </div>
        <div className="consequence">
          <span className={`badge ${live ? 'warning' : 'success'}`}>
            {live ? 'Engine observation' : 'Conditional calculation · illustrative inputs'}
          </span>
          <h4>Given that action, the calculated consequence is…</h4>
          <p>
            <code>{c[2]}</code>
          </p>
          <small>
            <strong>Limitations:</strong> {c[3]}
          </small>
        </div>
      </div>
      <section className="inset">
        <div className="row">
          <h4>Optional interaction simulation</h4>
          {onState && context.simulate && !live && (
            <label className="small">
              Simulation preview state
              <select
                aria-label="Simulation preview state"
                value={state}
                onChange={(e) => onState(e.target.value as SimulationState)}
              >
                {(['not_run', 'running', 'completed', 'incomplete', 'failed'] as const).map((s) => (
                  <option value={s} key={s}>
                    {s.replace('_', ' ')}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        {!context.simulate ? (
          <p>Interaction simulation skipped. Proposed actions were evaluated directly.</p>
        ) : (
          <>
            <span className={`badge ${state === 'failed' ? 'danger' : 'warning'}`}>
              {state.replace('_', ' ')} · {live ? 'engine swarm' : 'illustrative playback'}
            </span>
            {state === 'not_run' && <p>No discussion has been played.</p>}
            {state === 'running' && <p role="status">Running optional swarm rehearsal…</p>}
            {state === 'failed' && (
              <p role="status">
                {live
                  ? 'Simulation failed or was unavailable. Direct fuzz evaluation remains available; no completed discussion is claimed.'
                  : 'Simulation failed in this example. Direct action evaluation remains available; no completed discussion is claimed.'}
              </p>
            )}
            {(state === 'completed' || state === 'incomplete') && (
              <>
                {live ? (
                  <p className="small">
                    {state === 'completed'
                      ? 'Optional swarm rehearsal completed. Highlights appear in the effectiveness justification when available.'
                      : 'Discussion is incomplete. No agreed action or complete behavioral outcome is available.'}
                  </p>
                ) : (
                  <>
                    <div className="dialogue">
                      <strong>Employee — simulated</strong>
                      <p>
                        {index === 0
                          ? 'I have SGD 60 in prior meal claims and another SGD 50 claim. Can I submit the second one separately?'
                          : index === 1
                            ? 'The claim is exactly SGD 50. Do I need to attach a receipt?'
                            : 'The hotel claim is SGD 220 overseas. Which approval requirement applies?'}
                      </p>
                    </div>
                    {state === 'completed' ? (
                      <>
                        <div className="dialogue">
                          <strong>Manager — simulated</strong>
                          <p>
                            {index === 0
                              ? 'Let’s check the daily limit before submitting both claims.'
                              : index === 1
                                ? 'Attach the receipt while Finance clarifies the threshold wording.'
                                : 'Request manager approval while Finance resolves the conflicting exception.'}
                          </p>
                        </div>
                        <p className="small">
                          <strong>Proposed action ACT-00{index + 1}:</strong> {c[1]} This alternative is separate from the
                          original action evaluated below.
                        </p>
                      </>
                    ) : (
                      <p>Discussion is incomplete. No agreed action or complete behavioral outcome is available.</p>
                    )}
                  </>
                )}
              </>
            )}
          </>
        )}
      </section>
    </section>
  );
}

export function BehavioralComparison({
  context,
  accepted,
  onCompatibilityChange,
  findingsList,
  live = false,
  baselineLabel = 'SAMPLE-v1',
  revisedLabel = 'SAMPLE-v2',
  suiteLabel = 'DEMO-SUITE-15',
}: {
  context: SetupContext;
  accepted: number[];
  onCompatibilityChange?: (value: boolean) => void;
  findingsList?: UiFinding[];
  live?: boolean;
  baselineLabel?: string;
  revisedLabel?: string;
  suiteLabel?: string;
}) {
  const findings = findingsList?.length ? findingsList : mockFindings;
  const [mode, setMode] = useState('same');
  const comparable = live ? mode === 'same' : mode === 'same' && isSampleContext(context);
  useEffect(() => {
    onCompatibilityChange?.(comparable);
  }, [comparable, onCompatibilityChange]);

  return (
    <>
      <section className="panel">
        <span className="eyebrow">COMPARISON BASIS & REPRODUCIBILITY</span>
        <h3>What is held constant?</h3>
        <div className="basis-grid">
          <div>
            <strong>Policy versions</strong>
            <p>
              <code>
                {baselineLabel} → {revisedLabel}
              </code>
            </p>
          </div>
          <div>
            <strong>Scenario inputs</strong>
            <p>
              {suiteLabel} · same original IDs
            </p>
          </div>
          <div>
            <strong>Owner context</strong>
            <p>
              {context.goals.length} goals · {context.groups.length} groups · {context.assumptions.length} assumptions
            </p>
          </div>
          <div>
            <strong>Simulation</strong>
            <p>{context.simulate ? 'Enabled' : 'Skipped · direct action evaluation'}</p>
          </div>
        </div>
        <p className="small muted">
          {live
            ? 'Comparison uses the same engine run revised in place.'
            : 'Model, seed, suite hash, and engine version: not available until backend integration.'}
        </p>
        {!live && (
          <label className="field">
            Comparison basis preview
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="same">Same inputs</option>
              <option value="changed">Changed assumptions example</option>
              <option value="additional">Additional scenarios example</option>
            </select>
          </label>
        )}
        {!comparable && (
          <div className="notice warning" role="status">
            Like-for-like comparison unavailable:{' '}
            {mode === 'additional'
              ? 'additional scenarios belong in a separate cohort.'
              : 'owner context differs from the original sample.'}{' '}
            Existing sample safeguards are illustrations only and do not validate these changed inputs.
          </div>
        )}
      </section>
      {comparable ? (
        <>
          <section className="panel">
            <span className="eyebrow">SECTION A · FIXED-ACTION RULE COMPARISON</span>
            <h3>Same actions, different policy versions</h3>
            <p className="small muted">
              {live
                ? 'Baseline observations versus revision instruction targets from the engine run.'
                : 'Isolates the rule change. These sample transitions are illustrative, not engine results.'}
            </p>
            <div className="table-scroll" tabIndex={0} role="region" aria-label="Fixed action comparison">
              <table>
                <thead>
                  <tr>
                    <th>Scenario / action</th>
                    <th>Baseline rule outcome</th>
                    <th>Revised rule outcome</th>
                    <th>Goal result</th>
                  </tr>
                </thead>
                <tbody>
                  {findings.map((f, i) => (
                    <tr key={f.scenario}>
                      <td>
                        <code>
                          {f.scenario} · ACT-00{i + 1}
                        </code>
                        <p>{f.facts}</p>
                      </td>
                      <td>{f.observed}</td>
                      <td>{accepted.includes(i) ? f.after : 'Unchanged — finding not selected'}</td>
                      <td>{accepted.includes(i) ? (live ? 'Targeted in revision' : 'Target addressed in sample') : 'Remaining'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="panel">
            <span className="badge warning">Exploratory · not a fixed-action regression result</span>
            <h3>Behavioral response comparison</h3>
            <p className="small muted">
              The same starting scenario can lead to different hypothesized choices. Changes below are examples, not
              measured behavioral effects.
            </p>
            {accepted.length ? (
              accepted.map((i) => {
                const f = findings[i];
                if (!f) return null;
                const c = choiceFor(i, findingsList ? f : undefined);
                return (
                  <div className="inset" key={i}>
                    <h4>
                      {f.scenario} · {f.title}
                    </h4>
                    <div className="two-col">
                      <div className="hypothesis">
                        <strong>Before · possible response</strong>
                        <p>{c[0]}</p>
                        <small>{c[2]}</small>
                      </div>
                      <div className="consequence">
                        <strong>After · alternative possible response</strong>
                        <p>{c[1]}</p>
                        <small>
                          {live
                            ? 'Revision instruction targets this finding; actual post-revision behavior depends on the new IR.'
                            : i === 0
                              ? 'If the employee requests clarification before reimbursement, the SGD 10 excess may be avoided. Approval is not guaranteed.'
                              : 'If the clarification is followed, the corresponding action may satisfy the revised requirement. Actual behavior is unknown.'}
                        </small>
                      </div>
                    </div>
                    <p className="small">
                      <AlertTriangle size={14} /> Remaining uncertainty: awareness of the revised policy, compliance with
                      it, and manager response time are not established.
                    </p>
                  </div>
                );
              })
            ) : (
              <p>No revision selected for behavioral comparison.</p>
            )}
          </section>
        </>
      ) : (
        <section className="panel">
          <h3>Separate exploratory cohort</h3>
          <p>
            No backend results are available for the changed context or additional scenarios. Fixed-action and behavioral
            comparisons are withheld.
          </p>
        </section>
      )}
    </>
  );
}
