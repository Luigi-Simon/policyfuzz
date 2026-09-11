# Right to Disconnect demo — failed before native simulation

Inspected on 11 September 2026 at approximately 12:20–12:23 Singapore time
(UTC+08:00), following the user's request to monitor the run, explain the frontend
failure and record bugs for later fixes. No source changes, restarts, new workflow
submissions or provider calls were made. Browser evidence sections were expanded
to read the exact run identity. Policy text, prompts and credentials are excluded.

## What the frontend actually shows

This is a new failed attempt, distinct from the successful noon workweek simulation.

- Title: Right to Disconnect (After-Hours Communication) Implementation.
- Workflow/run ID: `32f84a65-4f55-4b2f-b8bb-1baeab0ac6b9`.
- Sandbox request ID: `c8c0909c-5492-45b3-aaec-2c8d1074b859`.
- Request fingerprint:
  `4a28d693c94b66ecc2ab6aac32f4391f68486fe403f00f16294f28b16ea5f8bd`.
- Policy SHA-256:
  `ed6117a3aa0d0f2dad19692fdce2af969fd7bcfd09bf155a036bec841cc38fe1`.
- Live mode, 20 requested participants.
- Orchestrator: completed.
- Metric: needs clarification, zero cases.
- Sandbox: **failed**, zero configured participants, zero observed participants,
  no personas and no stakeholder messages.
- Sandbox error: `sandbox_execution_failed: The provider response or job binding
  could not be validated.`
- Judge: partial / insufficient evidence. No validated pros or cons.
- Overall workflow: partial.

The user's screenshot captures Judge's section, not the Sandbox status above and
below it. There are two independent blockers: a real Sandbox setup failure and
the existing unsupported-policy limitation in Metric.

## Health is good; this simulation was never created

At 12:20:23, the backend health endpoint returned HTTP 200 in approximately 33 ms,
with `status=ok`, `live_configured=true` and `mirofish=reachable`. MiroFish extension
health returned HTTP 200 in approximately 17 ms. Provider health is explicitly
`configured_not_checked`; these endpoints do not test persona generation.

Backend process 82566 and the MiroFish extension process 82565 were running from
the expected integration checkout and native engine installation. No native
`run_twitter_simulation.py` process appeared in the process snapshot.

The exact failed fingerprint is absent from the durable job journal. At 12:22:43,
its engine job lookup returned HTTP 404 with `code=job_not_found`. There is no
native simulation ID for this attempt. The latest saved simulation remains the
earlier workweek run `sim_24f833040eb5`, completed at 12:06:00; it is not evidence
that the newer Right to Disconnect attempt succeeded.

The service log records the new fingerprint's initial job lookup at **12:18:52**
returning 404, followed by the workflow POST returning HTTP 200. No prepare or
start request appears between those entries. An initial 404 is expected for a
new request; it should be followed by participant generation and engine preparation.
HTTP 200 on the workflow POST means a typed workflow result was returned, not
that every agent succeeded.

## Diagnosis and confidence

**Confirmed:** this attempt failed before a native MiroFish simulation was created.
The services being online did not guarantee that participant setup would succeed.

**Strongly indicated by the call sequence:** participant generation or validation
failed after the initial job lookup. `sandbox/service.py:114–121` performs lookup,
generates the roster, checks its count, then calls native prepare. The observed
request never reached native prepare/start and returned an empty Sandbox result.

**Not recoverable from the retained evidence:** the exact underlying provider or
roster rejection. `sandbox/language.py:57–78` replaces provider exceptions,
incomplete/refused output and schema failures with one sanitized language error.
`personas()` can also reject a wrong count, duplicate names, non-English output or
seed-review failure. `sandbox/service.py:166–170` replaces those errors with the
generic Sandbox failure without preserving a safe stage/reason code in a log or
durable attempt record. A provider timeout can also be wrapped by this path;
there is no basis to rule it out merely because the UI says failed rather than
timeout. Do not claim a rate limit, invalid key, duplicate name or output truncation
was the actual cause without further evidence.

Twenty participants is within the configured 50-participant cap. The current
evidence does not establish that the requested count itself caused the failure.
No retry was launched during this monitoring pass, so there is no recovery result.

## Bugs and gaps to fix later

1. **High-priority Sandbox setup failure.** The user received no participants or
   simulation evidence. First add safe, request-bound diagnostics to determine
   whether failure occurs in roster generation, structured parsing, exact-count
   validation, name uniqueness or roster review. Then address the specific cause.
   Consider bounded correction of malformed/invalid rosters before native side
   effects, preserving exact count, seed requirements and truthful failure states.
   Do not bypass validation or repeatedly launch simulations as a repair strategy.

2. **High-priority diagnostic gap: pre-launch failures lose their reason and history.**
   The failed attempt is visible only in the browser and generic access-log
   entries; the job journal begins at native prepare. Preserve a safe failure-stage
   code, sanitized exception category, timestamps and workflow/request identity for
   failures before engine creation. Keep full policies, raw prompts, provider
   response bodies and secrets out of public errors and committed artifacts.
   Relevant paths: `backend/app/v2/sandbox/language.py`, `sandbox/service.py`,
   `workflow.py`, and the future durable workflow-attempt store.

3. **Confirmed Judge reporting bug: it claims nonexistent dialogue remains available.**
   The hardcoded unsupported-Metric summary in `judge/service.py:94–111` says
   stakeholder discussion remains available even when Sandbox failed with zero
   messages. Its headline and next steps focus on the Metric limitation and omit
   the immediate participant-setup failure. Branch this explanation on actual
   Sandbox availability/status; when both inputs are missing, identify both.
   Keep the recommendation gate closed and do not invent stakeholder findings.

4. **Existing Metric coverage gap.** The current executable domains do not cover
   after-hours communication windows, continuous rest, standby compensation,
   role-specific exceptions, anti-discrimination or pilot review obligations.
   This policy therefore produces no Metric tests. The earlier GST change added
   a bounded set of numeric-condition probes; it did not add a general employment
   policy interpreter. Extend the supported model with reviewed requirements and
   deterministic assertions; keep unclear or unsupported outcomes unscored.

5. **Existing UI wording issues recur.** The input helper describes only the
   reimbursement format despite the newer numeric-condition path. The zero-case
   Metric panel still says its cases cover a reimbursement model, and the empty
   participant panel says personas were generated. Make these descriptions depend
   on actual stage outcomes/counts. The page address is now `/v2`, so the old GST
   fragment issue is not present in this inspection.

The correct explanation of the screenshot is: **Judge has no recommendation
because Metric has no supported interpretation; separately, Sandbox failed during
pre-launch setup and supplied no discussion at all.** The native engine service
itself was responsive and was not observed crashing in this attempt.

## Local evidence

- Current `/v2` result with the exact run and fingerprint above.
- User screenshot taken at 12:19:50 SGT, showing Judge advice.
- `/tmp/policyfuzz-v2-fixed-app.log`, particularly line 303 and the immediately
  following workflow response at inspection time.
- Read-only journal query against
  `/Users/a123/Desktop/mirofish/MiroFish/backend/uploads/policyfuzz-v2-jobs.sqlite`.
- Read-only health, exact-fingerprint lookup and process checks described above.

There was no active native run for this request to keep monitoring. This note
records the terminal failure for later fixes; no ongoing automation was created.

## Subsequent implementation and retest

The user subsequently authorized immediate fixes. See the
[consolidated fix record](INCIDENT-FIXES-2026-09-11.md) for bounded roster recovery,
safe pre-launch diagnostics, unscored Metric scenario planning, qualitative Judge
review, corrected UI states and a successful 20-participant/two-round native run.
The original rejection's exact cause remains unknown; the old code did not retain it.
