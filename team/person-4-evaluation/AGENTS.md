# Person 4 — Deterministic evaluator
## Mission

Own the pure-Python source of truth for rule execution, evidence, structured patch safety, regression, benchmark scoring, and metrics.

## Paths owned

- `backend/app/features/evaluation/`, matching evaluation-feature tests, `team/person-4-evaluation/`.
- Benchmark execution artifacts and deterministic labels under `samples/benchmarks/` as scoped by the local rules.

## Paths prohibited

- Never import or call an LLM/provider. Do not edit shared contracts/protocols, API/core/workflow, dependencies, policy/fuzzing internals, frontend, final submission source, or another person's evidence.
- Do not access sealed blind labels before the defined reveal/scoring step.

## Public inputs and outputs

- Consume only public immutable domain artifacts and frozen-suite inputs.
- Produce predicate/validation results, effect/compliance resolution, authoritative traces, grouped findings, atomic patch results, regression/acceptance reports, metrics, benchmark scores, and owned evidence.

## Ordered tasks

1. Task 5 — Typed predicate execution and rule-set validation.
2. Task 6 — Effect resolution, overrides, and compliance.
3. Task 7 — Assertions, traces, and deterministic execution.
4. Task 16 — Deterministic finding construction and grouping.
5. Task 17 — Structured revision validation and atomic application.
6. Task 18 — Frozen-suite regression, acceptance gates, and metrics.
7. Task 21 responsibilities — frozen suites, expected effects, defect manifests, benchmark execution/scoring, and evaluation evidence.

## Required tests

- Cover every typed operator and invalid combination, overrides/cycles, all six effect states, compliance semantics, trace determinism, finding fingerprints, patch invariants, all seven acceptance gates, metric denominators, replay, and benchmark exact matching.

## Definition of done

- Evaluation is model-free and deterministic, no hidden defaults exist, traces cite all inputs, findings are grouped by stable cause, patches cannot mutate unrelated artifacts, and regression/metric outputs reproduce exactly.

## Handoff evidence

- Begin only after the public-contract freeze. Record interfaces, commits, files, focused/full test and replay commands, engine/suite/result hashes, benchmark/manual-review evidence, score basis, and limitations in `HANDOFF.md` and owned evidence files.
