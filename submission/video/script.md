# PolicyFuzz demo narration

**DRAFT — NOT RECORDED. DO NOT PRESENT AS A COMPLETED DEMO.**

Target: 4:40 (280 seconds), digital-solution video.

This text is ready for rehearsal, but recording is blocked until the `demo-core-v1` build, Gate B report, frozen metrics, approved capture set, and final wording review exist. Braced `{{metric:*}}` tokens are deliberate blockers. Replace each with one canonical metric claim containing, in order, the key, display value, data type, run mode, verification status, and blind-eligibility label. The exact syntax is documented in `metrics-template.json`; the verifier binds all six fields to the exact metric and source.

The demo uses a **synthetic** policy. The run-mode label must say **live** or **cached** according to the footage actually used. Any cached sequence must keep its badge visible. The benchmark-v2 **blind** material remains **unverified** for headline gold scoring until independent human review is complete.

## 0:00–0:20 — Problem hook

Policies get careful prose review, but they rarely get the equivalent of unit tests. PolicyFuzz explores a narrow test-and-evaluation question: can a reviewer turn policy intent into cited, executable scenarios, expose a concrete gap or conflict, and retest a confirmed revision without handing judgment to a model?

**Capture dependency:** approved opening slide and a verified `demo-core-v1` landing frame.

## 0:20–0:45 — User and manual-review pain

Our working user is a Finance or People Ops reviewer. The problem statement is still a hypothesis, not validated market research: edge cases span thresholds, exceptions, and interacting clauses, while a manual pass gives little reusable regression evidence. We compare the tool only with two bounded internal review exercises, never with claims about customers.

**Evidence dependencies:** completed manual-review records for `{{metric:manual_review_1_minutes}}` and `{{metric:manual_review_2_minutes}}`.

## 0:45–1:10 — Compile and confirm cited rules and intent

On the frozen build, we upload the synthetic policy. The proposed rules retain source citations, and unsupported language stays visible instead of being silently normalized. The reviewer checks the structured contract and explicitly confirms it before generation can continue. This pause is the first trust boundary: interpretation is proposed by a model; authority stays with the reviewer and deterministic validators.

**Capture dependency:** a clean run showing policy citations and the contract-confirmation control.

## 1:10–2:25 — Three development defect demonstrations

First, the threshold case. We select the exact witness around the receipt boundary and open its trace. The capture must show the cited rule, resolved values, and deterministic assertion state that support the finding.

Second, the hotel interaction. One clause says hotels below the cap need no approval regardless of destination, while another says international hotels need manager approval. We show the conflict witness and both citations together. The narration must follow the displayed trace; it must not imply that the system resolved legal meaning.

Third, the split-claim case. Separate meal claims can each sit under a per-claim cap while defeating the confirmed intent when considered together. We show the scenario inputs, the invariant witness, and the trace that connects the observed behavior to the reviewer-confirmed intent.

These are three seeded defects in the planned synthetic development fixture. Final narration may call them found only if the frozen run and evidence manifest contain the exact witnesses, traces, citations, and one-to-one manifest matches.

**Capture dependencies:** verified development report, three witness views, trace views, citation views, and artifact hashes from the same frozen commit.

## 2:25–2:50 — Measured coverage and one targeted cycle

The provisional suite exposes which supported dimensions remain uncovered. The system may request one bounded targeted generation cycle, then reruns the combined scenarios before freezing. In the final take, describe coverage only from the approved before-and-after coverage evidence. Report `{{metric:development_seeded_defect_recall}}` separately as development seeded-defect recall, with the synthetic-data label on screen.

**Capture dependency:** approved before-and-after coverage evidence, before-targeting coverage view, one generation event at most, and the post-targeting provisional view.

## 2:50–3:25 — Finding decisions and confirmed revision

PolicyFuzz pauses again. Candidate findings cannot be accepted, and structural findings need reviewer severity. We select only the findings supported by the frozen evidence, then inspect a structured revision proposal. Nothing is published automatically. The revision is applied only after session confirmation, and the confirmation event must be visible in the capture.

**Capture dependency:** finding-review and revision-confirmation states from one continuous verified session.

## 3:25–3:55 — Exact-suite retest and seven gates

After confirmation, deterministic Python reruns the identical frozen suite. The comparison checks all seven gates: suite identity, target fixes, failures outside targets, protected cases, newly bad states, unrelated-rule signatures, and holdout deterioration. Show the exact suite hash before and after. State the regression result only from `{{metric:development_regression_pass_rate}}`.

**Capture dependency:** frozen-suite identity and complete patch-acceptance report from the verified run.

## 3:55–4:20 — Trust boundary and safeguards

Models interpret language, generate bounded tests, and draft a proposal. They do not assign authoritative verdicts, severity, scored answers, hashes, or patch acceptance. Deterministic code owns those decisions. Human confirmation gates contract acceptance, finding decisions, and revision application; the public view excludes prompts, credentials, and full uploaded text.

**Capture dependency:** final architecture visual approved against frozen implementation evidence.

## 4:20–4:40 — Evidence, value, limits, close

This small internal benchmark includes `{{metric:scenario_count}}` scenarios, `{{metric:confirmation_count}}` confirmations, `{{metric:model_call_count}}` model calls, a total run time of `{{metric:total_run_time_seconds}}`, and provider cost `{{metric:provider_cost_usd}}`. The blind score `{{metric:blind_seeded_defect_recall}}` remains blocked unless independently reviewed and scoring-eligible. PolicyFuzz offers review coverage and repeatable regression evidence; it does not prove compliance or exhaustive discovery.

**Evidence dependencies:** finalized metrics manifest, reviewer-approved wording, and final repository link.
