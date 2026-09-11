# Four-day workweek demo — noon monitoring record

Observed on 11 September 2026, 12:07–12:10 Singapore time (UTC+08:00).
This is a separate run from the earlier workweek incident. The user requested
health monitoring and a bug record for later fixes. Application code, service
configuration and the displayed result were not changed, and no new simulation
or model call was made. One deterministic Metric replay was performed locally.

The run had already completed when first inspected at 12:07:09. Findings below
come from the retained browser result, native logs, action records, SQLite data,
status files and subsequent health checks; they are not continuous observations
of the original execution. Submitted policy text, seeds and prompts remain local
and are not copied into this note.

## Result

No runtime failure was found in the inspected evidence.

- Orchestrator completed.
- Sandbox/MiroFish completed: 10 requested/configured/observed participants,
  2 rounds, 23 successful comment actions and 33 displayed messages
  (10 seeded opening posts plus 23 comments).
- Metric returned `needs_clarification`: zero cases, no passing or failing
  assertions and no pass rate. Its current prose compiler does not execute
  working-hours, rest-day, overtime, salary-preservation or pilot-review rules.
- Judge returned `partial` / `insufficient_evidence`. Its deterministic evidence
  gate withheld a recommendation because Metric provided no supported
  interpretation. This gate does not call the Judge model.
- Overall `partial` therefore reflects the remaining Metric capability gap,
  not a failed MiroFish simulation or a new Judge service failure.

## Identity and timing

- Title: Four-Day Workweek Implementation.
- Workflow: `d34f13c8-4b22-4f82-884c-3f5662be13df`.
- Native simulation: `sim_24f833040eb5`.
- Request fingerprint:
  `41718050d1d4ba5547d5d940e2e02d852c1ccd23ea58795573cfd6056659160c`.
- Exact policy SHA-256:
  `dbf42128b4fe6b58c623f5f12ae14fa58c0046aa3aa2a97f6ea2eeefe6249b04`.
- Settings: 10 participants, 2 rounds, 240-second Sandbox deadline.
- 12:05:33: initial lookup returned 404 because the job had not yet been created.
  This is the expected idempotency lookup, not a workflow error.
- 12:05:40.171447: native process 89007 started.
- 12:05:46.244492–12:05:52.859636: round 1, 13 actions.
- 12:05:52.861609–12:05:58.047532: round 2, 10 actions.
- 12:05:58.049303: native progress recorded completion.
- 12:06:00.255116: native manager recorded completion; captures returned HTTP 200
  and the workflow POST returned HTTP 200.

The native process took approximately 20 seconds from launch to manager completion.
That excludes earlier preparation and later public evidence processing. More than
one action per participant per round is permitted; 23 actions for 20 participant
turns is not itself a count defect.

## Health and consistency

At 12:07:14, backend and engine health returned HTTP 200 in approximately 80 ms
and 6 ms respectively. At 12:10:24, the final checks were:

- Backend workflow health: HTTP 200, approximately 71 ms; `status=ok`,
  `live_configured=true`, `mirofish=reachable`.
- MiroFish extension health: HTTP 200, approximately 3 ms; `status=ok`.
- Exact job lookup: HTTP 200, approximately 16 ms; `status=completed`.
- Provider status was `configured_not_checked`. These read-only checks did not
  call the provider or certify its future availability.

Backend, MiroFish and frontend listeners remained available on ports 8002, 5002
and 5173. Process 89007 had exited. The job journal already stored `completed`
before the final API lookup. The previous stale-journal bug did not recur.

`policyfuzz_progress.json`, `run_state.json` and `state.json` agree on completion,
two rounds and 23 actions. The progress file has no pending agents or error;
`env_status.json` reports stopped. The database contains 10 users, 10 posts and
23 comments; every user authored comments, and SQLite `quick_check` returned `ok`.

The action file contains 23 action records plus five lifecycle events, with no
`success=false` action. The inspected simulation, social-agent, environment,
platform, recommendation and table logs contained no ERROR/WARNING/CRITICAL,
Traceback, TimeoutError or Exception markers. This is limited to retained logs;
it does not prove every transient provider condition would have been logged.
All actions were comments, so this run does not independently retest quote-first
feed handling. The `action_metadata_only` note remained informational and did not
downgrade the completed Sandbox stage.

## Follow-up backlog — recorded, not fixed in this pass

1. **High-impact existing capability gap: workweek rules cannot be executed.**
   The numeric-condition support added for GST covers age, income, home annual
   value and property count; it does not cover hours, rest days, overtime,
   scheduling, salary preservation or temporal review obligations. A local
   deterministic replay of this exact submission confirms zero cases. Add a
   reviewed executable workweek model and independent assertions, keeping
   operational exceptions and unclear terms explicitly unscored. Do not bypass
   Judge's evidence gate to make the workflow appear complete.
   Relevant code: `backend/app/v2/metric/conditions.py` and `metric/service.py`.

2. **Low-priority UI wording bug: capability and result labels are misleading.**
   The input helper still describes only the reimbursement format, omitting the
   supported numeric-condition path. With zero cases on this workweek run, the
   results also say that the cases cover a reimbursement model. Render wording
   from the actual interpretation/status, and avoid implying any model ran when
   there are no executable cases.
   Locations: `frontend/src/v2/WorkflowApp.tsx:56` and
   `frontend/src/v2/WorkflowEvidence.tsx:28`.

3. **Low-priority evidence ordering issue: numeric IDs sort as strings.**
   The browser lists round-1 comments as `1, 10, 11, 12, 13, 2, 3, ...` and seeded
   posts as `1, 10, 2, ...`. Native comments share an integer round timestamp, so
   `capture.py:154` falls back to lexicographic source-ID ordering. This is a
   presentation issue; the UI explicitly says sequence is presentation order,
   and there is no evidence of lost messages or broken reply links. Consider
   stable numeric ordering for same-kind native IDs while preserving parent-first
   ordering. Do not infer wall-clock timing where source records lack it.

4. **Low-priority navigation issue: a previous run's fragment remains in the URL.**
   The page displays `sim_24f833040eb5`, but its address still ends with a GST
   message fragment for `sim_1541cabdd148`. That fragment has no matching message
   in the current result. `WorkflowApp.tsx` replaces results without reconciling
   the fragment. Clear or update obsolete evidence anchors when replacing a run;
   do not reload the stateless page as a workaround. The current report itself
   has the correct run identity; no cross-run evidence mixing was observed.

## Evidence locations

- Native directory:
  `/Users/a123/Desktop/mirofish/MiroFish/backend/uploads/simulations/sim_24f833040eb5`.
- Native job journal:
  `/Users/a123/Desktop/mirofish/MiroFish/backend/uploads/policyfuzz-v2-jobs.sqlite`.
- Shared local service log: `/tmp/policyfuzz-v2-fixed-app.log`, run-specific
  entries around lines 252–275 at the time of inspection.
- Retained `/v2` browser result with workflow and native IDs above.

Raw native files can include policy text and prompts. Keep them local. No source
changes, restarts, stop requests, additional provider calls or ongoing automation
were needed: the identified workflow was already terminal before inspection.
