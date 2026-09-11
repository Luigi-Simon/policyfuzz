# Incident follow-up: executable employment comparisons and cited advice

This follows the user's request to fix the full incident backlog, including the
[13:05 Right to Disconnect run](RIGHT-TO-DISCONNECT-RUN-2026-09-11-1305.md).
Earlier runtime, roster, diagnostic, ordering and UI corrections remain described
in [the first consolidated fix record](INCIDENT-FIXES-2026-09-11.md).
Historical incident evidence is retained; no historical result was rewritten.

## Changes

- **Employment coverage:** Metric now executes explicit rest-duration, calendar-day
  notice and weekly-hours comparisons. Integer-minute conversion and fixed boundary
  truth vectors are deterministic. Source offsets and hashes bind each extracted
  comparison. Optional, negated, malformed and unsupported syntax stays unscored.
  A standard workweek reference alone does not become an enforceable maximum.
  The special `may ... only with ... notice` grammar retains only the notice
  threshold, without interpreting the rest of that permission.
- **Exact incident replay:** the submitted Right to Disconnect input now produces
  two passing comparison cases (720 minutes of rest and 30 days of notice), zero
  failures and ten unscored cases. The original all-unscored output remains a valid
  record of the old runner. These new passes test an interpreted comparison model,
  not an independent workplace implementation or the complete policy.
- **Remaining interpretation:** clock windows, endpoint inclusivity, timezones,
  alternative blackout/delay implementations, compensation, retaliation, opt-outs
  and operational exceptions remain explicit unscored questions. The combined
  outcome case is retained even with a one-case budget. Mixed money/duration inputs
  preserve both sets of units and limitations. Judge may still appropriately return
  `partial / insufficient_evidence`; a partial result does not establish engine failure.
- **Scenario relevance:** generic eligibility now asks about applicability when
  circumstances change. It does not invent a benefits application or delivery
  process merely because the source says “eligible employees.”
- **Discussion exposure:** the owned OASIS adapter rotates a five-post view by
  participant and round before limiting it. Older openings remain discoverable,
  self-replies remain blocked, and no message or reply target is rewritten.
  Participant instructions request a concrete contribution from their own background
  without forcing disagreement or a particular policy verdict.
- **Quality diagnostics:** duplicate wording across different native authors and
  replies concentrated in two opening threads are flagged without discarding source
  records. These visible quality limitations do not falsely turn successful capture
  into engine failure. Judge receives the limitations. The concentration diagnostic
  currently triggers at six or more replies, five or more openings and at least
  75% of replies in the two most-discussed opening threads; it is a descriptive
  heuristic, not a population statistic or proof of a single root cause.
- **Citation scope:** every cited finding has a separate check containing only its
  citations, relevant author names/reply IDs and the comparisons referenced by its
  own Metric actions. Uncited messages, other findings and unrelated persona
  biographies cannot supply support. The full-report review still checks summary,
  recommendation and provenance. Fixed Metric outcomes cannot be re-scored by Judge.
- **Comparison-only advice boundary:** local numeric extraction also uses the
  qualitative Judge path, with empty policy pros/cons and a withheld recommendation.
  Python supplies an exact-count summary instead of allowing a generated summary
  to describe unextracted provisions as absent. Usable discussion still reaches
  the real Judge for cited interactions and prospective review/testing actions.
  This closes a regression exposed when employment inputs first became executable.
- **Bounded repair:** only rejected finding prose is repaired against its fixed
  citations. Other findings stay unchanged. Local validation, global review and
  isolated citation checks run again. Calls are limited to four concurrent checks
  under the original Judge deadline; approved identical checks are reused.
  If individual findings still fail after the repair budget, only independently
  accepted findings survive in a visibly partial report. The rejected draft's
  summary/recommendation are replaced by a deterministic explanation and a withheld
  recommendation. Omission is disclosed. Provider failure and timeouts still fail
  explicitly; no substitute simulation or invented finding is returned.
  Repair uses a writing prompt separate from the validation prompt. Instructions
  to rewrite the finding/report are rejected as invalid user-facing next steps.

## Acceptance work and remaining uncertainty

The first synthetic live run used all four agents, 20 stakeholders, two rounds,
12 Metric cases and an eight-minute Sandbox deadline. Its identity was
`8b7c3673-7a8f-4550-bf76-d0a149e609cf`, native simulation `sim_f15905e078df`,
fingerprint `c5303a3c5009a37cd6794ba518b3cc614d59895534ee3db7a365435c2220234e`.
It ran from 13:49:16 to 13:51:25 SGT. Metric returned 3 pass / 0 fail / 9 unscored;
Sandbox completed both rounds with 20 posts, 40 comments and all 20 commenting
authors. No pending agents or native error remained; the environment stopped normally.

That run exposed two remaining issues rather than being counted as a successful
acceptance: rotating all 19 peer posts still produced 32/40 replies in two threads,
and whole-draft Judge regeneration exhausted its repair budget on citation claims.
These observations led to the five-post view and targeted repair above. Exact
duplicate comments were absent. A recorded-evidence Judge diagnostic also exposed
a false rejection of an inclusive maximum; checks now receive the exact referenced
comparison definition and explicit authoritative-verdict semantics.

The second run (`419f0025-2e30-4d14-bfba-1817912cda6c`, `sim_be9e75309220`,
fingerprint `341051ac929491369ad09b0b280e736eb319632664b1f34041fc10396f4e2ccf`)
verified the five-post feed: 20 participants, 40 actions, 60 messages, no exact
duplicate comments and replies to 11 openings. The top two threads received 14/40
replies (35%), compared with 32/40 (80%) in the first acceptance attempt. This is
an observed improvement in a synthetic retest, not a causal population estimate.

That second report passed automated checks, but manual frontend inspection still
found unsupported policy-absence claims and repair commentary in next steps. It
was not counted as full acceptance. It led to the comparison-only advice boundary,
deterministic summary, separate repair-writing prompt and local prose guard above.

## Final acceptance: 14:10:00–14:11:33 SGT

- Workflow: `edad1f49-ced9-426e-a196-ae6c8c7d14c7`.
- Sandbox request: `d1713187-17d8-4e3c-892f-8f9cfff44b10`.
- Native simulation: `sim_1cb0519b7f5f`.
- Fingerprint: `403fa70e62ccaa727fb412428dae65e45c4464a8553bc7836e38efc7659579d0`.
- The same synthetic employment policy was submitted through the frontend, with
  20 stakeholders, two rounds, budget 12 and an eight-minute Sandbox limit.
  Participant model stayed `gpt-4o-mini`; Judge stayed `gpt-4.1`.
- All four five-person roster batches succeeded on their first attempt. Native
  rounds completed at 14:10:43 and 14:10:53, with 20 actions each. The environment
  stopped normally; progress reported no pending agents and no error.
- Native storage contains 20 opening posts and 40 comments, with all 20 participants
  authoring comments. Replies reached 13 opening threads; the top two received
  15/40 replies (37.5%). No duplicate-wording or concentration diagnostic fired.
  Capture reported no missing links or source-order issues.
- Metric returned **3 pass / 0 fail / 9 unscored**. Judge returned **partial /
  insufficient_evidence**, two prospective next steps and one cited interaction.
  Its summary reports exact model-test counts; policy pros/cons remain empty.
  One finding failed the first isolated citation check, was repaired in place, and
  passed the second local/global/isolated review. No omission fallback was needed.
- Frontend accepted the final response. Manual review matched the cited interaction
  to post 4/comment 1 and the proposed scheduling/communication checks to comments
  16/29. The report contains no asserted policy defects or leaked repair commands.
  Overall partial status reflects unscored policy coverage, not a failed agent.
- Final health checks: backend 200 (108 ms), engine 200 (2 ms), frontend 200 (103 ms),
  frontend proxy health 200 (14 ms). No native simulation worker remained running.
  Native simulation and agent logs contained no ERROR/WARNING/Traceback/Exception/
  TimeoutError diagnostic lines in the scan. The browser's captured warning/error
  log was empty. These checks cover available logs, not hypothetical unlogged errors.

## Verification and handoff

- Final complete backend suite: **1,867 passed, 2 subtests passed**.
- Final v2 suite: **333 passed, 2 subtests passed** before the complete-suite run.
- Frontend suite: **234 passed**; the 28 workflow tests also passed after the final
  employment fixture refresh. Production build and generated frontend type checks
  passed. Subsequent Judge corrections are backend-only.
- API, Judge and Sandbox schema/fixture drift checks, Ruff and `git diff --check`
  passed. Legacy v1 model/artifact paths were not edited.
- Native offline smoke: real installed OASIS, ten fake participants, two rounds,
  20 actions, 30 captured post/comment records and **zero model calls**. This
  covers feed/quote expansion and shutdown using the installed native library.
- Services remain running: launcher 98616, MiroFish 98617, backend 98618, frontend
  98619; ports 5002, 8002 and 5173. The development restart reloaded the stateless
  frontend. Historical native records and incident notes remain available.
- Changes are local and uncommitted on `p1/fix-v2-agent-integration`, alongside the
  existing integration changes. No teammate worktree or native MiroFish source was edited.

Reproduction commands:

```sh
backend/.venv/bin/python -m pytest backend/tests -q
backend/.venv/bin/python -m pytest backend/tests/v2 -q
npm --prefix frontend run test:run -- --maxWorkers=1 --testTimeout=30000 --hookTimeout=30000
npm --prefix frontend run build
npm --prefix frontend run check:generated
PYTHONPATH=backend backend/.venv/bin/python -m app.v2.export_api --check
PYTHONPATH=backend backend/.venv/bin/python -m app.v2.export_judge --check
PYTHONPATH=backend backend/.venv/bin/python -m app.v2.export_contracts --check
/Users/a123/Desktop/mirofish/MiroFish/backend/.venv/bin/python scripts/check_v2_native.py
backend/.venv/bin/ruff check backend/app/v2 backend/tests/v2
git diff --check
```

The original 12:18 setup rejection's precise cause is still unknown because the old
implementation discarded its diagnostic detail. New safe attempt records address
future diagnosis, not recovery of evidence that never persisted. Language-model
generation remains variable; no finite regression suite guarantees arbitrary prose
coverage or zero future provider errors.
