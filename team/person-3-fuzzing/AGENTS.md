# Person 3 — Fuzz-test designer
## Mission

Build a bounded, reproducible scenario planner that combines exact mechanical cases with oracle-free exploration and freezes a coverage-qualified suite.

## Paths owned

- `backend/app/features/fuzzing/`, matching fuzzing-feature tests, and `team/person-3-fuzzing/`.

## Paths prohibited

- Do not edit shared contracts/protocols, API/core/workflow, dependencies, policy/evaluation internals, samples owned by other persons, frontend, submission, or private blind materials.

## Public inputs and outputs

- Consume confirmed public policy/contract models, stage protocols, coverage observations, and provider-neutral exploratory facts.
- Produce mechanical and exploratory candidates, validation/rejection records, canonical scenarios/stable IDs, coverage evidence, planner decisions, and a frozen `ScenarioSuite`.

## Ordered tasks

1. Task 8 — Mechanical scenario synthesis and exact boundaries.
2. Task 9 — Oracle-free exploratory scenario generation.
3. Task 10 — Scenario validation, deduplication, and stable IDs.
4. Task 11 — Coverage observation, one adaptation, and suite freeze.
5. Task 21 responsibilities — support deterministic benchmark scenario generation without owning authoritative expected effects or labels.

## Required tests

- Cover threshold minus/equal/plus cases, domain boundaries, complete facts, rejection reasons, assertion-origin restrictions, deterministic IDs/merges, 15-scenario cap, rule/invariant coverage, one targeted cycle, and coverage-limit termination.
- Tests use fakes and never call a live provider.

## Definition of done

- Identical inputs yield the same accepted suite/hash, every accepted scenario validates, LLM candidates supply no scored answers, coverage evidence is honest, and adaptation stops within fixed limits.

## Handoff evidence

- Begin only after the custody gates and public-contract freeze. Record interfaces, commits, files, focused/full test commands, seed/hash/cardinality evidence, rejected counts, achieved coverage, adaptation decisions, and limitations in `HANDOFF.md`.
