# PolicyFuzz pitch deck — draft outline

Status: **reviewable prototype draft; current cached rehearsal measured; frozen submission evidence pending**

This nine-slide draft follows the approved Task 24 narrative and now reports the current public cached rehearsal record. That record is synthetic, uses four scripted model responses and zero actual provider calls, and is not blind-scoring-eligible. `demo-core-v1`, the Gate B report, six-hour freeze, final browser capture, final metrics manifest, and two human reviews remain unavailable. No final-build screenshot or headline blind score is claimed.

1. **Policies have prose reviews, but no unit tests**

   Hook and narrow claim: PolicyFuzz is a prototype for turning a session-confirmed travel-and-expense policy interpretation into traceable scenarios and deterministic checks.

2. **One owner carries every edge case in their head**

   Finance / People Ops user hypothesis, current manual review burden, and the question the prototype is designed to test.

3. **The journey ends in a retest, not a summary**

   Upload or paste synthetic/non-confidential text; confirm cited rules and intent; fuzz boundaries and combinations; review a structured revision; retest the identical frozen suite. Live/cached mode labels remain visible.

4. **Coverage can freeze without an adaptive call**

   `plan -> act -> observe -> freeze -> retest`. The current cached rehearsal met the configured minimum coverage in its initial provisional suite, so `targeted_cycles` is zero. One targeted cycle remains a bound, not a step every run must use.

5. **Models propose; deterministic Python decides**

   Target modular-monolith architecture and explicit trust boundary. LLM-backed stages interpret or propose; Python validates citations and schemas, resolves effects, freezes/hashes suites, evaluates traces, computes metrics, and gates patch acceptance.

6. **Three cached findings make ambiguity executable**

   The current cached synthetic record contains three deterministic baseline findings: receipt requirement, approval requirement, and daily category cap. The authored demonstration decisions accept all three. Exact browser witness, trace, and citation capture remains pending the frozen build.

7. **The cached rehearsal closes all three findings**

   Current public cached rehearsal: 10 scenarios, 3 baseline findings to 0 remaining, 12 inconclusive assertions to 12 passing assertions, and all seven patch-acceptance gates true. Minimum coverage was already satisfied, so no targeted generation call occurred. These are rehearsal measurements, not frozen headline benchmark results. Gate B verification still precedes the `demo-core-v1` tag and six-hour freeze; the late-sealed blind candidate remains human-review-pending and scoring-ineligible.

8. **The impact hypothesis is better review evidence**

   Hypothesis: systematic boundary and combination coverage can make review more repeatable and regression-aware. No time, cost, savings, or ROI claim is made before measurement.

9. **A narrow prototype with a clear finish line**

   Limits, safety, five-person ownership, repository link, and closing claim: the intended proof is traceable evidence that a confirmed structured change fixes targeted failures without introducing protected regressions.

## Approved repository sources

- `docs/superpowers/plans/2026-09-04-policyfuzz-implementation.md`, Task 24 and the Gate B freeze procedure.
- `docs/superpowers/specs/2026-09-04-policyfuzz-design.md`, §§11–19, especially the evaluation, demonstration, acceptance, and positioning sections.
- `submission/evidence/benchmark-v2/README.md` and `provenance.json`, public candidate limitations only.
- `samples/cached-demo/summary.json` and `run-record.json`, current public synthetic cached rehearsal measurements.
- `team/person-1-integration/HANDOFF.md` and `team/person-5-product/HANDOFF.md`, current implementation status and limitations.
