# Demo incident fixes and live verification — 11 September 2026

Changes are applied locally on `p1/fix-v2-agent-integration`, base `efedfeb`.
Existing integration work and separate contributor worktrees were preserved.
No native MiroFish source, v1 contracts, or historical run artifacts were changed.

**Later follow-up:** [employment comparisons, discussion exposure and isolated Judge citation checks](INCIDENT-FIXES-2026-09-11-1400.md).

## Incident coverage

This pass used the [first workweek incident](FOUR-DAY-WEEK-RUN-2026-09-11.md),
[GST incident](GST-VOUCHER-RUN-2026-09-11.md),
[noon workweek incident](FOUR-DAY-WEEK-RUN-2026-09-11-NOON.md) and
[Right to Disconnect failure](RIGHT-TO-DISCONNECT-RUN-2026-09-11.md).
The historical observations remain unchanged; this record describes subsequent fixes.

- **Participant setup:** generate at most five people per batch, retain validated
  batches, exclude prior names, and verify exact count, unique names, English and
  seed constraints. Invalid batches allow two repairs. Authentication, permission,
  refusal and quota failures stop without retrying. Transient connection, timeout,
  rate-limit and server failures allow one retry within the existing workflow
  deadline. Respect the server's Retry-After delay or skip the retry if it exceeds
  the bounded wait. Never launch a smaller or fabricated replacement roster.
- **Pre-launch diagnostics:** locally persist run identity, Sandbox request identity
  and fingerprint, UTC times, stages, fixed error codes, attempt numbers and counts
  in `backend/cache/v2-diagnostics.sqlite`. This starts before provider calls and
  native preparation. No policy text, seed, prompt, raw provider body or exception
  message is recorded. Separate task contexts prevent concurrent-run contamination.
  Public Sandbox errors now identify the failing stage and sanitized category.
- **Metric participation:** unsupported ordinary prose now receives bounded,
  explicitly unscored scenario questions. Employment topics include communication
  windows, rest, standby, unequal treatment, operational exceptions and review.
  Generic scenarios cover ordinary, boundary, overlapping, interrupted and repeated
  requests. Topic offsets/hashes bind source matches without publishing the policy.
  The new `policy_scenarios` contract forbids execution traces, assertions, passing
  results, executable rules and a completed status. Malformed controlled-format
  reimbursement inputs still require clarification instead of being reinterpreted.
- **Judge handoff:** usable stakeholder discussion can now reach the real Judge
  even without executable Metric rules. That path is qualitative only: no policy
  pros/cons or revision/approval verdict; it returns cited interactions and checks
  to perform against the original policy. If both executable interpretation and
  usable messages are absent, the deterministic explanation identifies both gaps,
  including Sandbox setup/capture, and does not claim nonexistent dialogue exists.
- **Frontend:** descriptions distinguish executed tests from unscored scenario
  planning; zero-case and zero-persona panels no longer claim successful generation.
  Editing inputs/settings or starting another run clears obsolete evidence anchors
  while preserving form navigation. The Sandbox time limit is now visible and
  adjustable from one to ten minutes, with an eight-minute default.
- **Conversation ordering:** numeric native IDs at the same simulated time now sort
  numerically (1, 2, 10); opaque IDs still work. Parent messages remain before replies.
  Presentation order does not invent missing timestamps or prove causation.

Earlier fixes remain in place: quote-first OASIS feed handling, native action and
shutdown deadlines, real round/action progress, durable reconciled terminal status,
concurrent cancellation protection, neutral Metric-to-Sandbox handoff and the
informational treatment of action metadata. Their regression tests passed again.

Structured-output handling distinguishes refusal and incomplete output; transient
retries respect provider guidance. References: [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
[error and retry guidance](https://developers.openai.com/api/docs/guides/error-codes).

## Live acceptance through the frontend

Submitted a synthetic, non-confidential Right to Disconnect policy through `/v2`,
using seed `Singaporeans`, 20 participants, two rounds, budget 12 and a 480-second
Sandbox limit. This used newly authored synthetic text and a new run identity, rather than
replaying the failed historical request. Participant model remained the
existing `gpt-4o-mini`; Judge used the already-tested `gpt-4.1` override.

- Workflow: `a315ffa3-55a7-4708-8826-d796c7a4173b`.
- Sandbox request: `2936f710-8926-48b7-b474-feedd8b65f23`.
- Fingerprint: `78ff942b03ff244539c5c3e11a5595622a865b3708b50d927b70af23dcf501ec`.
- Native simulation: `sim_facf7123e646`.
- **12:47:22 SGT:** workflow started; Metric prepared 11 unscored scenarios.
- **12:47:25–12:47:46:** four batches generated and verified all 20 participants
  without a retry. Native preparation and start succeeded.
- **12:47:53–12:48:11:** both native rounds completed, 39 actions, no pending agents.
- **12:48:29:** Sandbox completed with 20/20 participants, 20 posts and 39 comments
  (59 messages). All 20 participants also authored at least one comment.
- **12:48:50:** Judge completed its evidence review. Its first draft was rejected
  during local validation; the second passed local and grounding validation.
  Recovery stayed within the configured bounds and no failed Judge result was returned.
- Frontend accepted the response and displayed all four stages, 11 unscored cases,
  three next steps and two cited stakeholder interactions. The native journal
  independently reported `completed`.

The overall result is **partial**: Orchestrator completed, Metric partial,
Sandbox completed and Judge partial / insufficient evidence. This is an explicit
coverage limitation, not a failed engine. The Judge model was called and its
validated qualitative report reached the frontend.

The new test does **not** recover the exact cause of the historical setup rejection;
those diagnostics were discarded by the old implementation. It verifies that the
new setup path handled 20 participants and that future failures retain safe reasons.

## Verification and remaining scope

- Final full backend suite: **1,838 tests and two subtests passed** (44.88 seconds).
- After final retry/diagnostic refinements: **304 v2 tests and two subtests passed**.
- Frontend: **233 tests passed**; production build, generated types and v2 contract
  exports passed. Lint and whitespace checks passed.
- Automated tests use fake providers. The separately identified frontend acceptance
  above is the live provider/MiroFish check.

Supported executable scoring remains limited to the controlled reimbursement model
and explicit numeric comparisons. Arbitrary employment/benefit prose still needs
reviewed executable requirements and an implementation adapter before pass/fail
scoring. Scenario planning does not close that domain-model gap or establish policy
readiness. No general-purpose policy approval is claimed.

Local runtime evidence: the safe diagnostic database above, the native simulation's
`policyfuzz_progress.json` and `twitter_simulation.db`, the native job journal and
the frontend result. Full result recovery after browser reload remains outside this
pass; safe attempt metadata and native evidence survive. Services were left running
for the user's next example.
