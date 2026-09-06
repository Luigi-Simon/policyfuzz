# PolicyFuzz demo narration

**DRAFT — NOT RECORDED. DO NOT PRESENT AS A COMPLETED DEMO.**

Target: 4:40 (280 seconds), digital-solution video.

This text is ready for rehearsal and now distinguishes the current public cached rehearsal record from final submission evidence. Recording remains blocked until the `demo-core-v1` build, Gate B report, six-hour freeze, approved capture set, and final wording review exist. Braced `{{metric:*}}` tokens remain deliberate blockers only for measurements the cached record does not establish. Replace them with canonical metric claims only after `verified-metrics.json` exists. The exact syntax is documented in `metrics-template.json`.

The demo uses a **synthetic** policy. The run-mode label must say **live** or **cached** according to the footage actually used. Any cached sequence must keep its badge visible. The benchmark-v2 **blind** material remains **unverified** for headline gold scoring until independent human review is complete.

## 0:00–0:20 — Problem hook

Policies get careful prose review, but they rarely get the equivalent of unit tests. PolicyFuzz explores a narrow test-and-evaluation question: can a reviewer turn policy intent into cited, executable scenarios, expose a concrete gap or conflict, and retest a confirmed revision without handing judgment to a model?

**Capture dependency:** approved opening slide and a verified `demo-core-v1` landing frame.

## 0:20–0:45 — User and manual-review pain

Our working user is a Finance or People Ops reviewer. The problem statement is still a hypothesis, not validated market research: edge cases span thresholds, exceptions, and interacting clauses, while a manual pass gives little reusable regression evidence. The two bounded manual-review exercises are still pending, so this rehearsal makes no speed or customer claim.

**Evidence dependencies:** completed manual-review records for `{{metric:manual_review_1_minutes}}` and `{{metric:manual_review_2_minutes}}`.

## 0:45–1:10 — Compile and confirm cited rules and intent

In the final take, we will upload the synthetic policy on the frozen build. Proposed rules retain source citations, and unsupported language stays visible instead of being silently normalized. The reviewer checks the structured contract and explicitly confirms it before generation can continue. This pause is the first trust boundary: interpretation is proposed by a model; authority stays with the reviewer and deterministic validators.

**Capture dependency:** a clean run showing policy citations and the contract-confirmation control.

## 1:10–2:25 — Three development defect demonstrations

The current public cached rehearsal record has exactly three deterministic baseline findings. First is a receipt-requirement finding. In the final capture, we select its exact witness and open the cited rule, resolved values, and deterministic trace.

Second is an approval-requirement finding. The final narration must follow the displayed witness and citations; it must not imply that the system resolved legal meaning.

Third is a daily-category-cap finding. We will show the scenario inputs, the invariant witness, and the trace that connects the observed behavior to the reviewer-confirmed intent.

All three are accepted by authored demonstration decisions in the cached record. That proves a reproducible rehearsal path, not independent human review or blind benchmark eligibility. Final narration may call them frozen results only when the Gate B evidence and capture show the same witnesses, traces, citations, and one-to-one matches.

**Capture dependencies:** verified development report, three witness views, trace views, citation views, and artifact hashes from the same frozen commit.

## 2:25–2:50 — Measured coverage and bounded adaptation

The current cached run accepted 10 scenarios. Its initial provisional suite already satisfied the configured minimum: all 10 rules and all three invariants were covered, with 23 of 26 predicate branches covered. The recorded `targeted_cycles` value is zero, so the workflow froze the suite without an adaptive model call. One targeted cycle remains available only when minimum coverage is missing. The rehearsal must not stage a fake adaptive cycle. Final development recall remains unstated until frozen benchmark evidence exists.

**Capture dependency:** approved frozen coverage evidence, `{{metric:development_seeded_defect_recall}}`, and a continuous event view that shows zero targeted cycles for this run.

## 2:50–3:25 — Finding decisions and confirmed revision

PolicyFuzz pauses again. Candidate findings cannot be accepted, and structural findings need reviewer severity. In the current cached rehearsal, authored demonstration decisions accept the three supported findings and produce a three-operation revision proposal. Nothing is published automatically. The revision is applied only after session confirmation, and that confirmation event must be visible in the final capture.

**Capture dependency:** finding-review and revision-confirmation states from one continuous verified session.

## 3:25–3:55 — Exact-suite retest and seven gates

After confirmation, deterministic Python reruns the identical frozen suite. In the current cached rehearsal, findings move from three to zero, all 12 previously inconclusive assertions pass, and every patch-acceptance gate is true: suite identity, target fixes, failures outside targets, protected cases, newly bad states, unrelated-rule signatures, and holdout deterioration. The final capture must still show the same suite hash before and after. Frozen development regression remains unstated until final evidence exists.

**Capture dependency:** frozen-suite identity, `{{metric:development_regression_pass_rate}}`, and complete patch-acceptance report from the verified run.

## 3:55–4:20 — Trust boundary and safeguards

Models interpret language, generate bounded tests, and draft a proposal. They do not assign authoritative verdicts, severity, scored answers, hashes, or patch acceptance. Deterministic code owns those decisions. Human confirmation gates contract acceptance, finding decisions, and revision application; the public view excludes prompts, credentials, and full uploaded text.

**Capture dependency:** final architecture visual approved against frozen implementation evidence.

## 4:20–4:40 — Evidence, value, limits, close

The current public cached rehearsal contains 10 scenarios, three accepted finding decisions, four scripted model responses, and zero actual provider calls. It is synthetic, cached, and blind-scoring-ineligible. Confirmation count, elapsed run time, provider cost, manual-review comparisons, and the blind score remain unstated until their required frozen or human evidence exists. PolicyFuzz offers review coverage and repeatable regression evidence; it does not prove compliance or exhaustive discovery.

**Evidence dependencies:** `samples/cached-demo/{summary,run-record}.json` for rehearsal counts; `{{metric:confirmation_count}}`, `{{metric:total_run_time_seconds}}`, `{{metric:provider_cost_usd}}`, `{{metric:blind_seeded_defect_recall}}`, finalized metrics manifest, reviewer-approved wording, and final repository link for submission claims.
