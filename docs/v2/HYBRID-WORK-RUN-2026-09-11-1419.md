# Hybrid Work live demo — 14:19 run inspection

Inspected on 11 September 2026, Singapore time (UTC+08:00), following the user's
request to monitor the active workflow and record observed bugs for later fixes.
This is a monitoring record: no application code, inputs or native records were
changed, no services were restarted, and no additional workflow or provider call
was submitted. The frontend result was inspected without reloading. Exact policy
text, raw provider output and credentials are excluded from this note.

This run follows the [14:00 incident fixes and acceptance](INCIDENT-FIXES-2026-09-11-1400.md).
The findings below are new observations of this particular user run, not changes
to the historical acceptance results.

## Identity and result

- Policy title: Hybrid Work Location (Telecommuting) Implementation.
- Workflow: `928cadf2-fb53-4533-a7f6-da5d0cf0401a`.
- Sandbox request: `747cf9c5-868a-4444-b8f7-8de92d61eee2`.
- Native simulation: `sim_be003282ba4f`.
- Request fingerprint: `81f0d340af93425dfdaf03c7088641750014e938237cdcdd7f8782c1338c89a3`.
- Policy SHA-256: `c644bd99e9166194f589291d87cc5db12dfe795074836dbe47a40e2f908104cd`.
- Metric suite SHA-256: `cf430dee23ca1881bc93b2783bf96ae8744cd2a867a0e71e6eef75dacff29d81`.
- Live mode; 20 stakeholders; two rounds; Metric budget 12; Sandbox limit 480 seconds.

All four product roles ran. Orchestrator completed; Metric returned **1 pass,
0 fail, 11 unscored**; Sandbox completed with **20/20** participants; Judge returned
**partial / insufficient_evidence**, three next steps and two interaction summaries.
Policy pros/cons are empty and the policy recommendation is withheld. The frontend
accepted the response and displays the same identity and counts as backend/native
records. Overall partial status reflects incomplete executable policy coverage;
it does not indicate a failed MiroFish engine.

## Timeline and health

Times below are SGT; backend diagnostic timestamps are UTC and were converted by
adding eight hours.

- **14:19:02.076:** workflow started; Metric finished partial at 14:19:02.121.
- **14:19:03.785–14:19:24.082:** four batches of five personas each completed on
  their first attempt. No roster repair or transient retry was recorded.
- **14:19:24.085:** native preparation; start requested at 14:19:24.172.
- **14:19:30.735–14:19:40.475:** round 1, 21 comment actions.
- **14:19:40.476–14:19:50.558:** round 2, 20 comment actions.
- **14:19:52.303:** native manager recorded completion and environment stopped.
- **14:20:10.165:** Sandbox evidence completed, 61 messages.
- **14:20:10.192–14:20:25.200:** Judge generation, full-report review and isolated
  citation checks all completed on the first attempt. No repair was triggered.
- **14:20:25.207:** workflow finished, **83.13 seconds** after submission.

Post-run checks returned HTTP 200 for backend workflow health (230 ms), MiroFish
health (2 ms), frontend page (103 ms), and the frontend-to-backend health proxy
(17 ms). These are individual reachability samples, not performance benchmarks.
Backend reports `ok`, live configured and MiroFish reachable. Its provider value
is deliberately `configured_not_checked`; actual roster/discussion/Judge progress
separately demonstrates provider use in this run.

Launcher 98616, MiroFish 98617, backend 98618 and frontend 98619 remained running.
Native worker 99427 had exited. Native journal, progress and manager state agree
on completed; both rounds are complete, pending agents is empty, error is null,
and environment status is stopped.

The current-run section of `/tmp/policyfuzz-v2-fixed-app.log`, beginning at line 668
at inspection, contains no ERROR/WARNING/Traceback/Exception/TimeoutError marker.
The only non-2xx request in that section is the expected initial job lookup 404
before preparation. Prepare/start/polls/capture and final workflow response succeed.
Native `simulation.log` and all five `log/*.log` files contain no matching diagnostic
markers. The browser's captured warning/error log is empty. These statements cover
available retained logs; content defects below did not produce runtime errors.

## Capture and discussion checks

Native storage has 20 users, 20 seeded opening posts and 41 comments: **61 messages**,
matching the frontend and Sandbox diagnostic count. All 20 participants authored
comments. There are no self-replies or missing comment parents. Parsing posts and
comments with the recorded `oasis_step_v1` clock returns 61 records and no errors.

The 41 comments are genuine source actions, not duplicated transport: participant
14 authored two distinct replies in round 1 (comments 15 and 16, to posts 19 and 17)
and one in round 2. Other participants each authored two comments. Native trace
counts are 41 create_comment, 20 seeded create_post, 40 refresh and 20 sign_up.
Two rounds do not impose exactly one model action per participant per turn.

Replies reach 13 of 20 opening threads. The two largest have 8 and 7 replies,
**15/41 = 36.6%**. No exact repeated-text group across different reply authors was
found by the current quality check, and no concentration diagnostic triggered.
This is better coverage than the earlier concentrated run, but does not establish
representativeness or substantive diversity. `action_metadata_only` is informational:
actions without stable IDs are retained internally rather than duplicated as messages.

## Confirmed issues for later fixes

### HW-J1 — Judge accepts a plural interaction supported by only one cited reply (P2)

The first interaction summary says a participant asked about inclusion and
**others replied** with communication/check-in/collaboration suggestions. Its own
citations are only **post 6 and comment 1**. Post 6 is the question from participant
5; comment 1 is one reply by participant 3. They support one respondent and the
listed suggestions, not multiple respondents.

Comments 33 and 34 elsewhere in the discussion also reply to post 6, but neither
is cited by this finding. This is incomplete citation scope, not proof that the
broader discussion never happened. The isolated checker explicitly instructs the
model to check quantities and every factual clause, yet accepted this item on
attempt 1. The frontend consequently labels the advice validated.

Future fix: constrain interaction wording to the number of independently cited
reply authors, or include the additional supporting replies. Add a synthetic
regression with several replies in the full discussion but only one in the
finding's citations. Relevant implementation: `backend/app/v2/judge/citations.py`,
`judge/evidence.py` and the Judge prompt/service; preserve source IDs and the
actual discussion. This is a recurrence of the citation-scope issue described in
the [13:05 incident](RIGHT-TO-DISCONNECT-RUN-2026-09-11-1305.md), despite the added check.

### HW-J2 — Judge describes questions as supported proposals (P2)

Next step 2 says numerous participants suggested mental-health supports, inclusive
practices and resources for remote client work. Its citations are **posts 12, 13
and 19** only. Those records ask, respectively, about mental-health measures,
access to remote-work technology, and support for client engagement. They do not
establish the claimed set of proposed supports or inclusive practices.

The prospective action to review these topics is reasonable. The defect is its
factual justification and citations: the broader replies contain proposals, but
the finding does not cite them. The isolated checker accepted this on attempt 1
too. Future fix: distinguish a question/concern from a proposal and require every
component of the justification to be supported by that item's citations. Narrow
the justification or cite actual proposal messages; add a synthetic question-only
regression. Do not turn the issue into a claimed defect in the submitted policy.

The second interaction (post 4/comments 2 and 3) does support its multiple replies
and proposals. The deterministic Judge summary accurately reports Metric counts;
no fabricated policy pass, asserted policy absence or leaked repair command was
observed in this report.

### HW-S1 — Requested seed groups are not established by the accepted roster (P2)

The seed requests a Singapore workforce including citizens, foreign Work Permit
holders and Employment Pass holders. None of the 20 retained persona descriptions
explicitly establishes citizenship or either pass category. Manual inspection shows
job/background descriptions, but does not establish the requested foreign-worker
groups. Names cannot be used to infer nationality or immigration status.

All four roster batches passed the seed-preservation review on their first attempt,
and no missing-group warning appeared. **20/20 attendance verifies participation,
not representation of the requested seed groups.** The observed defect is missing
auditable seed coverage and its accepted review; it does not prove what an unstated
persona nationality would have been.

Future fix: preserve explicit requested groups as reviewable roster attributes or
explicit background statements, check coverage across the complete roster, and
repair/disclose missing groups before claiming seed coverage. Do not invent group
quotas the user did not specify. Relevant implementation:
`backend/app/v2/sandbox/personas.py` and `sandbox/language.py:_roster_batch`.
The current reviewer receives each five-person batch separately and returns a
single `seed_constraints_preserved` boolean; that check did not catch this omission.

## Known capability gap, not a runtime failure

Metric's deterministic replay of the exact local input reproduces the frontend
policy hash, suite hash and 1/0/11 counts. It extracted one `notice_days >= 30`
comparison, source offsets 2041–2065, and tested values 29, 30 and 31 with expected
outcomes false/true/true. That is one case containing three boundary evaluations,
not three scored cases or independent verification of the policy.

The hours-based return-to-office notice, remote-day quotas, scheduling choices,
pilot/review timing, exceptions and other policy obligations are not executable
under this runner's current interpretation. Eleven remaining cases are explicitly
unscored. Calendar-day notice support does not imply support for an hours-based
notice clause or its emergency exception. Keep this on the capability backlog;
expansion requires explicit supported semantics and regression cases, not relabeling
unscored work as passed. Judge's withheld recommendation is expected with this
evidence. Its limited view also means it may ask for source-policy review of topics
already mentioned in the full policy; that is distinct from asserting they are absent.

## Evidence and handoff

- Frontend `/v2` result, matched through its expanded Workflow identity disclosure.
- `backend/cache/v2-diagnostics.sqlite`, events for the workflow ID above.
- `/tmp/policyfuzz-v2-fixed-app.log`, current-run interval starting at line 668.
- `/Users/a123/Desktop/mirofish/MiroFish/backend/uploads/policyfuzz-v2-jobs.sqlite`,
  completed job selected by the exact fingerprint above.
- `/Users/a123/Desktop/mirofish/MiroFish/backend/uploads/simulations/sim_be003282ba4f/`:
  progress, manager/environment state, native logs and `twitter_simulation.db`.
- Local deterministic Metric replay and capture/quality checks; no live model
  invocation was added by the inspection.

Only this incident note was added. Services and the completed result were left
available. This workflow is terminal, so no continuing monitor is needed for it.
The next fix should address the three recorded content/validation issues while
retaining honest partial coverage and the successful native execution path.
