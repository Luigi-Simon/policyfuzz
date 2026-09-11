# Four-day workweek run: health and bugs for later

Observed on 11 September 2026. Times below are Singapore time (UTC+08:00).
This is an observation record, not a fix or a policy assessment. Monitoring did
not restart services, stop the run, change settings, or make additional model
calls. The application's own deadline stopped the simulation. Full policy text,
participant prompts, provider credentials, and raw model records are omitted.

## Final result

- Workflow: **partial**. Orchestrator completed; Metric needs clarification;
  Sandbox partial; Judge partial. The browser retained the evidence and advice.
- Sandbox: **10 of 10 participants observed**, **22 stored messages**: 11 posts
  and 11 comments. This includes 10 seeded opening posts; it is not 22 completed
  model actions. Native logs recorded 12 completed actions.
- Round 1 completed; round 2 started but did not complete before the deadline.
- Metric: **0 cases**, no exact pass/fail conclusion. The current executable
  domain supports controlled reimbursement policies, not natural-language
  workweek policies. This is a known capability gap, not a successful test result
  or a runtime crash.
- At the final health check around 01:08, backend health returned HTTP 200 in
  53 ms, and the MiroFish job endpoint returned HTTP 200 in 19 ms with status
  `cancelled`. Native run state said `stopped`; process 75856 no longer existed.
  Both services remained responsive, although this simulation did not finish.
- The Judge returned advice, but its policy-omission claims require review;
  see issue 1. Passing the current validation did not establish factual grounding.

## Run identity

- Policy title: Four-Day Workweek Implementation.
- Workflow run: `9774afbc-cd55-48c5-b63a-3dad9eceb926`.
- Sandbox request: `f3223fd4-b5b8-4a0f-943d-a908d745d395`.
- Native simulation: `sim_9aded5381fcf`.
- Request fingerprint:
  `983261a12a7ec747079e6d8383460e9c477dbf679213243ac5b9b44b3623621e`.
- Requested settings: 10 participants, 2 rounds, Metric budget 12, Sandbox timeout
  240 seconds. The adapter reserves 20% of that deadline for evidence capture,
  so simulation preparation and execution receive roughly 192 seconds, less
  time already spent earlier in the request.
- PolicyFuzz branch: `p1/fix-v2-agent-integration`, base `efedfeb`, with the local
  integration changes present during this run. This was not a clean-base test.

## Timeline

- **01:00:48:** Initial job lookup returned 404. Expected for a new fingerprint;
  this alone is not an error.
- **01:00:55:** Native simulation prepared and started with 10 profiles,
  process 75856.
- **01:01:07.997:** Round 1 started.
- **01:01:13.695:** Round 1 ended; round 2 started immediately afterward.
- **01:01:15.281:** Last observed completed-action log entry. Ten actions had
  completed in round 1 and two in round 2. No later successful action entry was
  observed before shutdown.
- **01:03:58:** Sandbox deadline expired. The application requested stop;
  MiroFish sent SIGTERM to the simulation process group.
- **01:04:08:** Native process had not exited within its 10-second grace period;
  MiroFish escalated to SIGKILL. Evidence capture endpoints still returned 200.
- **01:04:09:** Native stop completed, and the stop endpoint returned 200. The
  native logger also reported simulation failure with `error=None`.
- **By 01:08:** Browser displayed the terminal partial workflow and Judge report;
  final health checks confirmed responsive services and no simulation process.

## Issues to fix later

### 1. Judge converts evidence gaps into unsupported policy omissions — P1

The accepted report says stakeholder questions signify provisions are not
explicit or sufficient, and claims the policy lacks explicit equity and working
parent support. The submitted form already contained related protections in
clauses 7 and 10 and performance/monitoring requirements in clauses 4 and 8.
Questions can support a request to check clarity; they do not establish absence
of those provisions. The report also presents the Metric parser's required
`Goal` clause/format as a policy deficiency. That requirement belongs to the
supported reimbursement input format, not to this policy's substance.

Confirmed boundary: `backend/app/v2/judge_contracts.py:34` supplies a title,
hash, Metric evidence and Sandbox evidence, not the original policy. With no
supported Metric interpretation, the Judge has no reviewed policy clauses on
which to base these absence claims. `backend/app/v2/metric/parser.py:18` supplies
the reimbursement-format clarification. The Judge prompt and review prompt
already prohibit converting simulated claims into verified policy defects, but
this report passed their current checks.

Later acceptance: unsupported domains must remain capability limitations;
participant questions must be attributed as questions; claims that a provision
is absent need reviewed source support. A synthetic regression should include
explicit safeguards plus participants asking about the same safeguards, and
verify that generation and review do not declare them missing.

### 2. Round 2 stops producing observable actions — P1; cause unconfirmed

Only two of the ten participants recorded a completed action in round 2. The
last completion was at 01:01:15, followed by no visible action progress until the
deadline at 01:03:58. Database contents remained at 11 posts and 11 comments.
The service remained reachable throughout, so HTTP health did not imply
simulation progress. No provider error or traceback establishing the stall's
cause was found in the inspected logs.

Later investigation: trace pending agent/provider calls and per-action timing
inside the native simulation step. Add useful stall diagnostics and bounded
failure handling without fabricating completed rounds. Reproduce with fake
slow/hanging agents before another live acceptance run.

### 3. Stop acknowledgement deadline races native shutdown — P2

The public result contains both `timeout` and `stop_unacknowledged`. Native
shutdown required its full 10-second SIGTERM grace period plus forced cleanup;
the endpoint returned 200 approximately 11 seconds after stop began. The
adapter's `_stop` allows only 10 seconds by default
(`backend/app/v2/sandbox/service.py:272`). Its timeout therefore precedes a
successful native acknowledgement. The public warning was accurate at that
instant but remained unresolved after the process stopped.

Later acceptance: align shutdown budgets or reconcile final stop status within
a separate bounded check. A fake native runner that ignores SIGTERM must verify
the forced-stop path, evidence retention, and final acknowledgement. Do not
remove the warning when termination is actually unknown. No orphan simulation
process remained in this observed run.

### 4. Native status files omit activity and retain stale state — P2

While SQLite and agent logs showed completed actions, native status reported
zero actions and an empty rounds collection. `run_state.json.updated_at` stayed
at 01:00:55 even after `completed_at` became 01:04:09. After termination,
`env_status.json` still said `running` with its 01:01:07 timestamp;
`state.json` said stopped but retained round 0 and `twitter_status=not_started`.

The wrapper in `backend/app/v2/sandbox/run_twitter_simulation.py:41` writes round
events to `twitter/actions.jsonl`, but does not emit the native action records
the runner's status counters consume. The final completed-round count of 1
out of 2 is consistent with one finished round; it should not itself be called
incorrect. The interface needs to distinguish completed rounds from the active
round and expose a reliable activity timestamp.

Later acceptance: reconcile actual actions with status counters, update
timestamps, and ensure all native status views reflect stopped/failed/completed
consistently after graceful and forced termination. Preserve failure reasons
instead of an unhelpful `error=None` shutdown diagnostic.

### 5. Legacy health label is ambiguous for the live workflow — P3

`GET /api/v2/health` returned `{"status":"ok","execution_mode":"fixture"}`
during this live run. `backend/app/v2/main.py:53` returns the legacy fixture
API's default `HealthResponse`; it does not describe the active workflow or
prove live dependencies are ready. This does not mean the simulation used
fixtures: native process, logs, database and job state establish live execution.

Later acceptance: clearly scope the legacy label and provide health/readiness
information for the configured workflow and engine without launching a model
call. Keep liveness separate from per-run progress and provider readiness.

## Local evidence for follow-up

- Backend/app log: `/tmp/policyfuzz-v2-app.log`.
- MiroFish service log: `/tmp/policyfuzz-mirofish-server.log`; lines 165–172
  capture the stop sequence observed here.
- Native simulation directory:
  `/Users/a123/Desktop/mirofish/MiroFish/backend/uploads/simulations/sim_9aded5381fcf`.
  Inspect `run_state.json`, `state.json`, `env_status.json`,
  `twitter/actions.jsonl`, `twitter_simulation.db`, and `log/social.agent.log`.
  The top-level `simulation.log` was empty; useful native logs were elsewhere.
- Read-only job journal:
  `/Users/a123/Desktop/mirofish/MiroFish/backend/uploads/policyfuzz-v2-jobs.sqlite`.
- The browser's current `/v2` result contains the public errors and Judge text.
  The assembled workflow UI is stateless; reloading clears that displayed result.

These locations are local troubleshooting references, not artifacts to commit.
Native logs and databases can contain source policy and prompts. This note saves
the relevant observations without copying those records into the repository.
No fixes or additional workflow runs were made during this monitoring pass.

## Subsequent fixes requested by the user

The user then requested immediate fixes. The following changes are on
`p1/fix-v2-agent-integration` in the integration checkout. The original observations
above remain the record of the earlier run; they are not rewritten as successes.

1. **Judge grounding:** if no supported Metric interpretation exists, a
   deterministic evidence gate withholds policy findings and returns
   `partial` / `insufficient_evidence` with concrete next steps. It explicitly
   reports that no Judge model was called. The parser now identifies its input
   restriction as a tool capability limitation. For supported interpretations,
   generation/review instructions also reject absence claims based on questions.
2. **Native stall:** reproduced an installed OASIS `UnboundLocalError` when a
   quoted post is the first item passed to its comment expander: `num_reports`
   was never assigned. That exception kills the platform dispatcher and leaves
   agents waiting on its channel. The owned peer feed now reads the quote and
   comment rows directly, preserving source IDs, authors and quote content.
   Unknown comment targets also no longer crash the wrapper. The original
   process did not retain its exception; this is a reproduced failure mechanism
   consistent with its first quote followed by stalled actions.
3. **Bounded execution and stop:** detect platform-task failure, bound individual
   actions after they acquire a concurrency slot, cancel sibling/queued actions
   on failure or cancellation, and propagate stop signals into an active step.
   Stop acknowledgement and reconciliation each have a 20-second bound; the
   outer Orchestrator has a 45-second cleanup allowance. Unknown termination
   remains a warning unless the exact fingerprint's terminal job is confirmed.
4. **Progress:** record real action metadata and separate active/completed rounds
   in `policyfuzz_progress.json`. Reconcile native counts, round summaries and
   timestamps; terminal state also updates the environment status file. Seeded
   openings and feed reads are excluded from participant action counts.
5. **Health:** added `/api/v2/workflows/health` and the lightweight MiroFish
   extension health endpoint. The legacy fixture health response stays compatible
   and its API description directs live-workflow checks to the new endpoint.
6. **Capture status, discovered during retest:** ordinary native action metadata
   lacks conversational message IDs and remains backend-only. Its informational
   note no longer makes a complete capture partial; genuine capture/translation
   limitations still do. Source messages are neither duplicated nor fabricated.

Native MiroFish source/dependency files and teammate worktrees were not edited.
These fixes live in PolicyFuzz's wrapper/integration modules and are loaded by
the restarted local services. The executable Metric domain has **not** been
expanded: natural-language workweek policies still have no scored Metric tests.

### Retest evidence

- Offline installed-engine check: `scripts/check_v2_native.py`, executed with
  MiroFish's Python. Ten deterministic synthetic participants completed two real
  OASIS rounds: 20 actions, 11 posts, 19 comments. No model calls. This checks the
  actual installed platform, channel, clock, SQLite and quote-first feed.
- Live synthetic workweek workflow:
  `7b3cc126-95ce-4ac5-a20f-a5fa1d8f1512`, native simulation
  `sim_50fb831e6a90`. Prepared at 01:58:23; native completion recorded at
  01:58:59. The full HTTP request took 57.5 seconds.
- All 10 participants were observed; both rounds completed with **20 actions
  and 30 messages**. Native state reported `completed`, two round summaries,
  20 actions and matching updated/completed timestamps. Environment status was
  `stopped`. Native progress had no pending agents and no error.
- Judge returned `partial` / `insufficient_evidence`, with no policy pros/cons,
  no Judge error, and an explicit statement that the model was not called.
  Metric correctly reported `needs_clarification` with zero tests. Overall
  workflow remains partial because that policy domain is unsupported.
- This live request exposed the informational-metadata status bug in item 6.
  After that fix, the exact completed job was replayed through capture using
  its previously verified English text. Capture returned `completed` with all
  30 message and source objects unchanged. No new simulation or model call was
  made for this replay. The original
  live response and the subsequent replay are separate artifacts.
- Local retest artifacts: `/tmp/policyfuzz-fixed-workweek-result.json`,
  `/tmp/policyfuzz-fixed-workweek-capture-replay.json`,
  `/tmp/policyfuzz-native-check.log`, and `/tmp/policyfuzz-v2-fixed-app.log`.
- Frontend: **219 tests passed**, using one worker and 30-second test/hook
  deadlines on this loaded host. The earlier concurrent run had eight
  five-second timeouts; assertions and repository test settings were unchanged.
  Production build/typecheck, generated-type checks, schema export checks and
  lint/diff-whitespace checks passed.
- Final backend suite: **1,788 tests and 2 subtests passed** in 102.33 seconds.
  The offline HTTP regression was run with localhost-port access; the initial
  restricted run had been blocked from binding a port. The clarified Metric
  message's generated Judge examples were regenerated and checked.
- After the final service reload, workflow health reported backend `ok`,
  MiroFish `reachable`, and provider `configured_not_checked`. A fixture-only
  HTTP workflow smoke test returned `completed` for all four stages. No new
  model call was made for these final checks. Local services remain running.
