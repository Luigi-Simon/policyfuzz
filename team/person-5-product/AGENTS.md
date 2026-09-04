# Person 5 — Product and demo lead
## Mission

Protect blind-test custody, build the `RunView`-only product experience, and produce evidence-led submission deliverables without overstating results.

## Paths owned

- `frontend/`, frontend tests/dependencies, `submission/`, `team/person-5-product/`, and the narrow exclusive Task 24 path `scripts/verify_submission.py`.
- Sole custody exception for sealed blind policy/labels and their defined reveal-time import paths.

## Paths prohibited

- Do not edit backend dependencies, shared contracts/protocols, API/core/workflow, specialist feature internals/tests, development/corrected artifacts, cached-demo artifacts, or other persons' evidence.
- Do not edit any other shared `scripts/**`; Person 1 owns those paths and only consumes `scripts/verify_submission.py` and its output during Task 25.
- Do not expose blind archive contents before the plan's reveal gates or create model extraction/fuzz implementation.

## Public inputs and outputs

- Consume generated API types and only the public `RunView`, plus verified handoff/evidence artifacts for submission claims.
- Produce Gate A1/A2 seal ledgers as separate custody actions, typed UI views/transports, revealed blind artifacts at the defined step, deck/video/checklist, and final submission evidence.

## Ordered tasks

1. Gate A1 — Seal blind source and human labels before schema work.
2. Gate A2 — Validate and seal schema-bound blind artifacts.
   - Blind custody continues non-blockingly while other work proceeds within its recorded gates; do not expose or import the sealed contents early.
3. Task 21 blind-custody responsibilities — keep the blind archive and labels sealed until reveal, then import only the defined artifacts.
   - Blind reveal/import must wait until Tasks 20 and 23 pass and the code, prompts, provider settings, and blind-run tools are frozen.
4. Task 22 — Typed React workflow and all four mock-backed views.
   - Task 22 may start after Task 4 freezes the public contract; it does not wait for blind reveal/import.
5. Task 23 — Live HTTP transport and bounded polling.
6. Task 24 — Nine-slide deck, 4:40 demo video, and deliverable checklist.
7. Task 25 contribution — final submission-source and checklist handoff to Person 1.

## Required tests

- Test seal validation/custody interfaces, generated-type drift, all four UI states, accessibility and user actions, mock/live transport, polling bounds/errors/deletion, and mechanical deck/video/evidence constraints.
- UI tests never call a live provider; blind labels remain inaccessible before reveal.

## Definition of done

- Custody gates are auditable without leaking contents, the UI consumes no backend internals, all product states remain accurately labelled, every claim traces to frozen evidence, and official size/slide/duration constraints pass.

## Handoff evidence

- Record seals and custody timestamps/hashes, commits, files, UI/build/test commands, live/cached observations, evidence keys, reviewer checks, deliverable hashes, and limitations in `HANDOFF.md`.
