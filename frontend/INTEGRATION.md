# Revised PolicyFuzz frontend — team handoff

## What you can use now

The four-screen React/Vite interface follows the second Stitch export and the revised owner → behavior → consequences → revision journey. Start it with `npm ci` and `npm run dev` inside `frontend`. Choose **Use sample policy** and confirm the interpretation. Review findings individually; structural findings require severity. Clarification blocks revision until an accept/reject decision replaces it. All results are explicitly illustrative.

This document is a **request for contract agreement**, not an authoritative API schema. Person 1 remains the sole shared-contract owner. The current checkout has no OpenAPI, generated RunView types, or canonical response fixture. No teammate should import `src/preview.ts` or `src/behavior.tsx` as backend domain models.

## Revised ownership and requested contributions

| Owner | Needed for the revised flow | Deliver to Person 1 / frontend |
|---|---|---|
| Person 1 — integration | Expand creation, confirmation, projection, orchestration and comparison contracts; freeze a revised contract version | OpenAPI, JSON Schema, generated public fixtures, allowed actions, stage/error states, version anchors and complete sample responses |
| Person 2 — policy | Keep source-derived rules separate from goals and assumptions; map owner-confirmed goals to supported constraints; propose revisions | Exact citations, unsupported clauses, interpretation review data, constraint provenance, structured change summaries and unverified prose |
| Person 3 — scenarios | Generate role/context-based responses and alternative choices; optional bounded discussion simulation | Stable scenario/actor/action IDs, group and assumption links, public rationale, simulated discussion summaries, selected proposed actions, simulation status and limitations |
| Person 4 — evaluation | Evaluate explicit proposed actions; compute conditional consequences; compare versions | Rule outcomes, traces, formula inputs/units, consequence provenance, independent assertions, fixed-action transitions, regression and comparison-validity results |
| Person 5 — frontend | Render and collect decisions using the agreed contract | This interface, interaction tests, and a future generated-type HTTP adapter |

The social simulation implementation owner and its execution limits need team agreement. Person 3 is the proposed owner based on scenario-generation responsibility; this handoff does not silently redefine other persons' charters.

## Data each screen needs

### 1. Setup and interpretation

- Policy identity/title/source and text submission; full uploaded text must not return in the public RunView.
- Goals: stable IDs, plain-language desired outcomes, owner confirmation, links to any supported machine-checkable constraints.
- Affected groups: stable IDs, operational role, context and relationship to the policy. Avoid demographic stereotypes.
- Assumptions: stable IDs, statement, source/rationale, confirmed/unconfirmed state and confirmation provenance.
- Optional interaction-simulation setting, off by default.
- Extracted rules, citations, unsupported clauses, confirmed interpretation, validation errors, and immutable setup revision/hash.
- Specify whether an unconfirmed assumption blocks execution or is carried forward as uncertainty. This preview carries it forward visibly.

### 2. Scenarios and behavior

- Stable scenario ID, immutable input facts, actor/group IDs, category, triggering condition, linked goal/assumption/rule IDs.
- Proposed choices/actions with stable action IDs, stated public rationale, dependencies and uncertainty. Do not provide unsupported likelihood percentages.
- Simulation status: skipped/not run/running/completed/incomplete/failed; bounded turn count; simulated role labels; public summaries; action references; partial-result/error information.
- Distinguish the original action from alternatives emerging from discussion. A discussion suggesting “ask a manager” must not be displayed as evidence for evaluation of a different “submit separately” action.
- Action evaluation: the exact action evaluated, expected constraint/provenance, resolved rule outcomes, assertions, compliance and source-bearing trace.
- Consequences: inputs, formula/method, units, calculated values, assumptions and conditions. A conditional SGD 10 reimbursement excess is not evidence that reimbursement occurred.

### 3. Findings and revision

- Finding ID, type, evidence level, review status, linked scenario/action/group/goal/assumption/rule IDs and tested policy version.
- Behavioral hypotheses remain separate from mechanically reproduced defects. Assumption-validation candidates are not automatically scored findings.
- Owner decisions: accept/reject/needs clarification, reviewer severity when appropriate, and clarification request status. Person 1 must specify whether clarification is a supported server action or a local pending state.
- Proposal ID, anchored baseline/context/suite, targeted finding IDs, typed operations, unverified draft wording and confirm/reject actions.

### 4. Comparison

- Immutable basis: original and revised policy refs, scenario suite/facts, owner goals, groups, assumptions, engine version and simulation configuration/model/seed where applicable.
- **Fixed-action comparison:** same action IDs and inputs evaluated against both versions, isolating rule changes.
- **Behavioral comparison:** separate exploratory outputs when proposed responses are regenerated. Same starting scenarios do not imply identical resulting actions or causal proof.
- Fixed, remaining, regressed/new, inconclusive and errored results, protected and aggregate holdout results, backend acceptance gates, metric numerators/denominators with N/A handling.
- Explicit comparison validity. Changed assumptions or extra scenarios must be a separate cohort, not silently added to frozen-suite totals.

## API connection

Use the existing planned Person 1 surface as the starting point:

| Action | Planned endpoint |
|---|---|
| Create | `POST /api/v1/runs` |
| Snapshot | `GET /api/v1/runs/{run_id}` |
| Interpretation decision | `POST /api/v1/runs/{run_id}/confirm-contract` |
| Finding decisions | `POST /api/v1/runs/{run_id}/select-findings` |
| Revision decision/retest | `POST /api/v1/runs/{run_id}/confirm-revision` |
| Delete | `DELETE /api/v1/runs/{run_id}` |

There are no separate Person 3 endpoints consumed by this frontend. Person 1 must decide whether optional simulation runs within orchestration or requires an additional command. Do not infer that the existing request schemas already support the new fields.

After agreement: generate TypeScript from frozen OpenAPI, validate public RunView snapshots at runtime, add typed transports and error handling, then replace local preview state. Poll active stages at 1.5-second non-overlapping intervals; stop at confirmation/terminal stages, abort stale requests, and send current expected artifact hashes with decisions.

## Fixture requests / acceptance examples

Please provide: sample success with simulation off; success with simulation on; simulation failure with direct evaluation retained; incomplete discussion; unconfirmed assumption; unsupported interpretation; clarification-pending finding; revision rejected; failed safeguard; changed comparison basis; additional-scenario cohort; expired/deleted run.

One complete fixture should link policy → confirmed goal → scenario → proposed action → evaluation → finding → revision → both comparison sections using stable IDs.

## Implementation map

- `src/App.tsx`: original four-step shell, rule review, scenario table, finding decisions, revision and safeguards.
- `src/behavior.tsx`: local setup form state, SetupEditor, BehaviorEvidence and BehavioralComparison components. These are presentation components, not backend contracts.
- `src/preview.ts`: original illustrative rules/scenarios/findings.
- `src/styles.css`, `src/behavior.css`: original Stitch palette and responsive extensions.
- `src/test/`: component/integration tests using local fixtures; no provider calls.

## Limits for the receiving team

No real extraction, behavior generation, social simulation, rule execution, calculated backend consequences, patch application, persistent storage, or live HTTP transport is implemented. Formula text uses fixed synthetic example inputs. Custom policy/context changes are not evaluated and are explicitly distinguished from sample evidence. Preview exports are labelled non-evidence. Browser visual/mobile QA and real backend integration still need joint verification.

The revised flow goes beyond the original approved design/plan. Person 1 should coordinate that scope revision before freezing contracts; this frontend handoff does not edit the shared plan or other owners' files.
