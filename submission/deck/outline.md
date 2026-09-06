# PolicyFuzz pitch deck — draft outline

Status: **reviewable prototype draft; validation evidence pending**

This nine-slide draft follows the approved Task 24 narrative while the final backend, `demo-core-v1`, Gate B report, scored development/control/blind artifacts, reviewer checks, and capture footage remain unavailable. It contains no measured-result claims and no final-build screenshots.

1. **Policies have prose reviews, but no unit tests**

   Hook and narrow claim: PolicyFuzz is a prototype for turning a session-confirmed travel-and-expense policy interpretation into traceable scenarios and deterministic checks.

2. **One owner carries every edge case in their head**

   Finance / People Ops user hypothesis, current manual review burden, and the question the prototype is designed to test.

3. **The journey ends in a retest, not a summary**

   Upload or paste synthetic/non-confidential text; confirm cited rules and intent; fuzz boundaries and combinations; review a structured revision; retest the identical frozen suite. Live/cached mode labels remain visible.

4. **One bounded cycle targets missing coverage**

   `plan -> act -> observe -> adapt -> retest`, with at most one targeted generation cycle before the suite is frozen.

5. **Models propose; deterministic Python decides**

   Target modular-monolith architecture and explicit trust boundary. LLM-backed stages interpret or propose; Python validates citations and schemas, resolves effects, freezes/hashes suites, evaluates traces, computes metrics, and gates patch acceptance.

6. **Three planned cases make ambiguity executable**

   Synthetic development cases: the exact-SGD-50 receipt threshold gap, the international-hotel approval conflict, and the split-meal daily-cap breach. Exact trace and citation capture remain pending the verified build.

7. **Measured results wait for a frozen evidence chain**

   Pending evidence plan for development, corrected control, and blind runs; Gate B verification precedes the `demo-core-v1` tag and six-hour freeze, followed by evidence capture and review checks. The late-sealed blind candidate is human-review-pending and scoring-ineligible.

8. **The impact hypothesis is better review evidence**

   Hypothesis: systematic boundary and combination coverage can make review more repeatable and regression-aware. No time, cost, savings, or ROI claim is made before measurement.

9. **A narrow prototype with a clear finish line**

   Limits, safety, five-person ownership, repository link, and closing claim: the intended proof is traceable evidence that a confirmed structured change fixes targeted failures without introducing protected regressions.

## Approved repository sources

- `docs/superpowers/plans/2026-09-04-policyfuzz-implementation.md`, Task 24 and the Gate B freeze procedure.
- `docs/superpowers/specs/2026-09-04-policyfuzz-design.md`, §§11–19, especially the evaluation, demonstration, acceptance, and positioning sections.
- `submission/evidence/benchmark-v2/README.md` and `provenance.json`, public candidate limitations only.
- `team/person-1-integration/HANDOFF.md` and `team/person-5-product/HANDOFF.md`, current implementation status and limitations.
