# GST Voucher example: health and follow-up record

**Update after the requested fixes:** the journal issue is fixed and verified.
Metric now executes bounded, source-linked numeric condition checks on the GST
input. Combined eligibility and benefit delivery are still outside that executor.
The original monitoring observations below remain historical; see the follow-up
verification at the end.

Checked on 11 September 2026, around 02:13–02:15 Singapore time (UTC+08:00).
The workflow had already finished by the first inspection. This record uses the
retained browser result, native event logs, status files, SQLite counts and final
health checks; it does not claim continuous observation during execution.
No code changes, service restarts, stop requests or additional model calls were
made during this monitoring pass. Full policy text and participant prompts are
not copied into this note.

## Outcome

**No new runtime failure was observed in this run.**

- Orchestrator: completed.
- Sandbox/MiroFish: completed, with **10 of 10 participants**, **2 completed
  rounds**, **22 recorded actions**, and **32 messages** (10 seeded opening posts
  plus 22 comments). Every participant ID appears in the action records.
- Metric: needs clarification, **0 tests**. This natural-language benefits policy
  is outside the current controlled reimbursement interpreter's supported input.
- Judge: partial / insufficient evidence. The evidence gate withheld policy
  findings and a recommendation because no supported interpretation was supplied.
- Overall workflow: partial because of the known Metric capability limitation,
  not an engine crash or failed capture. The informational action-metadata note
  did not incorrectly downgrade Sandbox this time.

## Identity and timing

- Title: GST Voucher – Heartland and Digital Readiness (HDR) Enhancement.
- Workflow run: `384f9196-d829-465d-a148-e489143f4601`.
- Sandbox request: `3f1853ef-8b1d-4fe6-a359-a56a914c8e20`.
- Native simulation: `sim_1541cabdd148`.
- Fingerprint:
  `e3ee0c6d0c7a179f850938447eb0f6f2470c716a2f4ca34307b43a448f56e3de`.
- Requested settings: 10 participants, 2 rounds, 240-second Sandbox deadline.
- **02:11:35:** native process 80354 started.
- **02:11:45.330–02:11:51.815:** round 1, 12 recorded actions.
- **02:11:51.816–02:11:57.073:** round 2, 10 recorded actions.
- **02:11:57.075:** native completion event, 22 actions total.
- **02:11:59.490:** native manager recorded completion, about 24 seconds after
  process launch. This duration excludes earlier policy/persona preparation and
  subsequent English evidence projection; it is not total HTTP request latency.

## Final health and consistency checks

At **02:14:29**:

- Backend `/api/v2/workflows/health`: HTTP 200, approximately 164 ms;
  `status=ok`, `live_configured=true`, `mirofish=reachable`.
- MiroFish extension `/api/policyfuzz/v2/health`: HTTP 200, approximately 2 ms.
- MiroFish job lookup: HTTP 200, approximately 8 ms, `status=completed`.
- Provider configuration was reported as `configured_not_checked`; the health
  check did not make a provider request or certify future provider availability.
- Backend, MiroFish and frontend listeners remained available on ports 8002,
  5002 and 5173. Native process 80354 no longer existed.

`policyfuzz_progress.json` reported completed, no pending agents, and no error.
`run_state.json` agreed: two completed rounds, 22 actions, two round summaries,
and matching updated/completed timestamps. `state.json` reported completed and
`env_status.json` reported stopped with the final timestamp.

The native event log contained no failed action entries. The inspected agent,
environment and platform logs contained no ERROR/WARNING/CRITICAL log entries
or traceback markers. `simulation.log` contained normal completion and environment
closure markers, with no error markers. The service log showed successful start,
capture and workflow responses; no timeout or forced-stop sequence was observed
for this simulation. These are findings from the retained logs, not proof that
every possible transient/provider issue would have been logged.

## Items for later

1. **Low-priority diagnostic inconsistency: persisted job status is stale.** The
   job journal still stores `status=running`, while native state and the public
   job lookup correctly return completed. `JobRegistry.lookup` overlays native
   status on the returned object without writing it back to SQLite
   (`backend/app/v2/sandbox/extension.py`). This did not prevent completion or
   mislabel the browser result. A direct journal reader can nevertheless mistake
   a completed run for active work. Decide whether to persist terminal states or
   explicitly document/name the stored field as a launch claim. Test restart and
   retry behavior if that persistence behavior changes. This is an observability
   follow-up, not an observed execution failure.
2. **Known capability gap: no general-policy Metric interpreter.** GST Voucher
   eligibility and benefit rules were not executed or scored. Supporting this
   domain requires a reviewed interpretation and meaningful deterministic cases;
   the absence of test results must remain visible. The Judge evidence gate
   behaved correctly, so this is not a recurrence of the earlier grounding bug.

No runtime bug requiring an immediate fix was found. The earlier stall, stale
native counters, incomplete stop state and false capture-status issues did not
recur in the inspected result. This run contained comments rather than quote
posts, so it does not independently retest the quote-first feed repair.

## Local evidence references

- Service log: `/tmp/policyfuzz-v2-fixed-app.log`.
- Native files:
  `/Users/a123/Desktop/mirofish/MiroFish/backend/uploads/simulations/sim_1541cabdd148`.
  Relevant files include `policyfuzz_progress.json`, `run_state.json`,
  `state.json`, `env_status.json`, `twitter/actions.jsonl`,
  `twitter_simulation.db`, `simulation.log`, and the `log/` directory.
- Read-only journal:
  `/Users/a123/Desktop/mirofish/MiroFish/backend/uploads/policyfuzz-v2-jobs.sqlite`.
- Browser: the current `/v2` result for the workflow ID above. Reloading the
  stateless page can clear the displayed result; it was not reloaded here.

Raw native records can contain submitted policy text and prompts. Keep them
local; this note records only the diagnostic observations needed for follow-up.

## Fix verification, approximately 02:35–02:38 SGT

- `JobRegistry.lookup` now persists reconciled status with a transaction and
  snapshot comparison. Terminal statuses survive an unavailable engine; a stale
  poll cannot replace a concurrent cancellation. Startup closes its claim
  transaction before a lookup can write. The original GST journal record was
  reconciled to `completed` by the updated endpoint, then confirmed with a direct
  read-only SQLite query.
- Metric now compiles supported prose comparisons rather than rejecting this
  entire input. The same GST text yields age ≥21 and assessable income ≤$34,000,
  each tested below, at and above its threshold: **2 passing cases, 6 probes**.
  A third combined-outcome case remains explicitly unscored. These are conformance
  checks of the interpreted comparisons, not tests of an independent payment or
  eligibility implementation. Numeric thresholds are source-bound, not hardcoded
  to the GST example. Unsupported clauses, component scope, tiers and proration
  remain a capability limitation; they are not silently assigned an expected answer.
- Shared v2 contracts, generated frontend types, UI trace rendering and Judge
  instructions now retain this distinction. Partial Metric evidence reaches the
  live Judge, whose pilot gate remains closed. Scenario IDs/titles/circumstances
  sent to Sandbox carry no Metric verdicts or expected outcomes.

Live verification used the same submitted policy and seed, 10 participants,
2 rounds and a 240-second Sandbox deadline:

- Workflow: `21ccf3a5-c42d-4679-beb8-3d6a5dfd007e`.
- Native simulation: `sim_5ceee3787ea8`.
- Sandbox completed: **10/10 participants, 2 rounds, 20 actions, 30 messages**.
- Native progress and run state both completed, no pending agents or error;
  environment stopped. Native manager completion: **02:37:08.637866 SGT**.
- New job journal status: `completed`, confirmed directly after the workflow.
- Judge returned validated cited advice with `revise_before_pilot`, `status=partial`
  and no errors. This is advisory feedback based on local checks and simulated
  concerns, not a deployment approval or proof of a policy violation.
- Overall `partial` now reflects explicitly unscored combined policy outcomes;
  neither Sandbox nor Judge failed. Local public response:
  `/tmp/policyfuzz-gst-fixed-live-result.json` (not committed).

Validation: final v2 regression suite, frontend's 223 tests, build/type generation,
schema export checks, lint and whitespace checks. The broader offline backend run
passed 1,815 tests plus 2 subtests; its legacy real-HTTP smoke test timed out while
checks and the live demo ran concurrently, then passed independently in 3.86 s.
The final v2 rerun also covers rejection of an action sent to the wrong executor.
No timeout thresholds or legacy assertions were weakened.
