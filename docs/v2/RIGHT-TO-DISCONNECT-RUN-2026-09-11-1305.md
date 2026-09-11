# Right to Disconnect demo — 13:05 run inspection

**Subsequent fixes:** see [the employment and citation follow-up](INCIDENT-FIXES-2026-09-11-1400.md).
The observations below remain the unchanged historical incident record.

Inspected on 11 September 2026 at approximately 13:11–13:16 Singapore time
(UTC+08:00), following the user's request to check frontend/backend logs and health
and record bugs for later. This was an inspection, not a fix or a new live test.
No services were restarted, no provider calls were added, and no policy inputs or
source code were changed. Evidence disclosures were expanded without reloading.
The exact policy was read locally for deterministic Metric replay; its full text,
raw model prompts/responses and credentials are excluded from this note.

## Run identity and outcome

- Policy title: Right to Disconnect (After-Hours Communication) Implementation.
- Workflow: `ac9f5054-1867-42e7-9ec7-0bc56eb5457e`.
- Sandbox request: `0f55a91c-0caa-40aa-9d4f-7cd4f7cc1f36`.
- Native simulation: `sim_22c2e2fe76c0`.
- Request fingerprint: `ad9838126359bf7dbdb073c782a9c282bc245d1174888e1c89af4f55d49c421c`.
- Policy SHA-256: `ed6117a3aa0d0f2dad19692fdce2af969fd7bcfd09bf155a036bec841cc38fe1`.
- Metric suite SHA-256: `499a442ac21ec8abfb88f1d5f6ac02adde6ba6310eaf8477813053e569672e5f`.
- Live mode; 20 participants; two rounds; test budget 12; Sandbox deadline 480 seconds.

Frontend, attempt records and native journal agree. Orchestrator completed; Metric
returned 12 unscored scenarios; Sandbox completed with 20 requested/configured/
observed participants; Judge returned partial / insufficient evidence with a
qualitative summary, three next steps and two cited interactions. Overall partial
reflects missing executable policy tests, not a failed MiroFish simulation.

Unlike the earlier 12:18 failure of the same policy text, this request reached
native preparation and completed. It also differs from the previous synthetic
verification run; do not mix their counts, seeds, fingerprints or Judge attempts.

## Timeline and health evidence

- **13:05:56.032:** workflow started. Metric finished scenario planning about 40 ms later.
- **13:05:57.487–13:06:21.747:** all four five-person batches passed on their first
  attempts. No roster repairs or transient language retries were logged.
- **13:06:21.839:** native start requested.
- **13:06:28.251–13:06:37.773:** round 1 completed, 20 actions from 20 participants.
- **13:06:37.774–13:06:47.980:** round 2 completed, 20 actions from 20 participants.
- **13:06:49.952:** native state recorded completion; environment stopped normally.
- **13:07:05.920:** Sandbox public evidence completed.
- **13:07:05.952–13:07:17.857:** first Judge draft and grounding review succeeded;
  no repair attempt or failed Judge result. Workflow finished at 13:07:17.864,
  about 81.8 seconds after submission.

At **13:12:23**, all four HTTP checks returned 200: backend workflow health
(about 193 ms), MiroFish health (about 2 ms), frontend page (about 96 ms), and
frontend-to-backend health through the proxy (about 12 ms). These are individual
observations, not a performance benchmark. Backend reported `ok`, live configured,
and MiroFish reachable. Health still reports provider `configured_not_checked`;
the successful calls in this specific run separately demonstrate provider use.

Backend PID 92130, MiroFish PID 92129 and frontend PID 92131 remained listening
on 8002, 5002 and 5173 respectively, under launcher PID 92128. No active native
simulation subprocess remained after this terminal run.

Native journal and progress both report completed, two completed rounds, 40 actions,
no pending agents and no native error. Database counts are 20 posts and 40 comments
for **60 messages**. All 20 people authored a post and comments; every recorded
action is a successful `create_comment`. The action log has 45 lines because five
are round/start/end lifecycle events; it does not contain 45 stakeholder actions.
There are no missing comment parents or self-replies.

The run's section of `/tmp/policyfuzz-v2-fixed-app.log` contains no error, exception,
traceback, warning or timeout marker. The initial job lookup returns an expected
404 for a new fingerprint, followed by successful preparation/start/status/capture
and a 200 workflow response (line 414 at inspection). No unexpected failed HTTP
request was found in that interval. Available frontend browser error/warning logs
were empty; the result rendered and its identity matched the backend. Native
`simulation.log` and the simulation's `log/*.log` files had no matching error,
exception, traceback, warning or timeout entries. This describes retained logs;
it is not a guarantee that every internal event was instrumented.

## Bugs and gaps recorded for later fixes

### 1. Metric still cannot execute this policy — P1 capability gap, confirmed

All 12 items use `policy_scenarios`, with empty execution traces/assertions,
`review.rules=null`, zero passes/failures and no pass rate. Replaying the deterministic
Metric planner locally reproduced the exact frontend suite hash. The earlier
reliability fixes made the role participate through scenario planning; they did
not implement scoring for employment communication windows, continuous rest,
standby compensation, exceptions or policy-review obligations.

Impact: this demo still cannot produce verified policy findings or an approval
recommendation. Judge's partial status and empty policy pros/cons are expected
guardrail behavior, not evidence of a missing Judge deployment.

Future fix: build and review executable requirements/adapters for the relevant
employment rules and their exceptions. Preserve unscored outcomes where requirements
are ambiguous; do not convert scenario templates into asserted passing tests.
Paths: `backend/app/v2/metric/service.py`, `metric/conditions.py`,
`metric/scenarios.py`, shared Metric contracts and matching fixtures/tests.

### 2. Metric selects an unrelated benefits-style scenario — P2, confirmed

`scenario-6`, “Eligibility and delivery,” describes circumstances changing between
an application and delivery. Its topic match is offsets **25:33**, the word
“eligible” in the employment-policy introduction. The broad `eligib\w*` alternative
in `backend/app/v2/metric/scenarios.py:50` selects the same application/delivery
template used for benefits. That process was not established from this policy.

Impact: a scenario-budget slot goes to an unjustified domain assumption, reducing
the relevance of the 12-item plan and passing that circumstance into Sandbox.
It remains unscored, so no false pass/fail was produced.

Future fix: distinguish employment eligibility from benefit application/delivery,
or use a domain-neutral question until source context establishes the process.
Add a synthetic regression case where “eligible full-time employees” alone must
not select a benefits-delivery scenario.

### 3. Stakeholder discussion converges and repeats — P2 quality issue, confirmed; cause not proven

Only five of the 20 opening posts receive replies. Parent distribution is:
post 20: 16 replies; post 19: 15; post 18: four; post 17: four; post 7: one.
Thus **31/40 replies (77.5%) target two opening posts**. Round 1 covers four parents,
round 2 covers three. Many comments restate feedback/review proposals, limiting
the range of discussion despite complete participant attendance.

Comments **31 and 40 are exactly identical text**, both replying to post 17 in
round 2, authored by native user IDs 8 and 19 respectively (Mei Xing and Vincent Ho
in the frontend). They have separate source IDs and successful native action
records. This is generated repetition, not a duplicated transport delivery.
Do not delete one source record merely because two people generated the same text.

The peer feed at `backend/app/v2/sandbox/peer_feed.py:20` sorts all same-step
openings by descending post ID and includes existing comments. That is a plausible
contributor to concentrated attention and imitation, together with model/persona
behavior. This observation alone does not establish the cause or prove a general
failure across different seeds. No controlled rerun was performed here.

Future fix: test feed-order sensitivity, broader exposure and personality-specific
responses; flag duplicate/near-duplicate generation in quality diagnostics while
preserving raw source identity. Assess diversity separately from “20/20 observed.”

### 4. Judge interaction citation coverage is incomplete — P2, confirmed

The second “Key stakeholder interactions” item describes Vincent Ho's opt-out
question leading to multiple proposals for **regular feedback and flexible
approaches**, but cites only **post 20 and comment 2**. Those two records support
the opt-out question and Mark Lee's flexibility proposal. Regular feedback is
discussed in comments **5 and 8**, which are cited in the separate next-step item,
but not in this interaction claim. One cited reply also does not establish the
claimed multiple proposals by itself.

The broader discussion contains supporting material, so this is a citation-scope
defect rather than a wholly invented discussion. The first interaction's cited
post 7/comment 1 pair does support its summary. Judge's grounding review accepted
the current draft on the first attempt, demonstrating that passing validation
does not guarantee every compound claim has sufficient citations.

Future fix: require each part of a compound interaction summary to be supported
by its own cited records, or narrow the summary to the single cited reply. Review
`backend/app/v2/judge/prompts.py`, `judge/evidence.py` and `judge/service.py:204`.
Use a synthetic test where feedback exists elsewhere in the payload but not in
the cited pair; structural ID/reply validation alone must not suffice.

## Items that did not recur

No pre-launch roster failure, engine stall, shutdown timeout, stale terminal journal
state, missing participant, translation fallback, malformed public response or
frontend console failure was observed. Numeric message order is correct (posts
1–20, then comments 1–40). The current URL has no obsolete evidence fragment.
`action_metadata_only` remains informational; it did not downgrade Sandbox.
Judge did not assert missing policy provisions or manufacture policy pros/cons.

## Evidence locations

- User screenshot at 13:10:19 and the current `/v2` result with the run identity above.
- `backend/cache/v2-diagnostics.sqlite`, queried by the exact workflow ID.
- `/tmp/policyfuzz-v2-fixed-app.log`, run lookup starting at line 387 at inspection.
- `/Users/a123/Desktop/mirofish/MiroFish/backend/uploads/policyfuzz-v2-jobs.sqlite`.
- `/Users/a123/Desktop/mirofish/MiroFish/backend/uploads/simulations/sim_22c2e2fe76c0/`:
  progress/state files, `simulation.log`, `log/*.log`, `twitter/actions.jsonl` and
  `twitter_simulation.db`.

Only this incident note was added. The completed run and all services were left
in place. No ongoing monitor is needed for this already-terminal request.
