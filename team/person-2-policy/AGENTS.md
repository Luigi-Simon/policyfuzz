# Person 2 — Policy intelligence
## Mission

Turn bounded synthetic policy text into validated, cited rules and minimal revision proposals without crossing deterministic trust boundaries.

## Paths owned

- `backend/app/features/policy/`, matching policy-feature tests, `team/person-2-policy/`.
- Development/corrected files under `samples/policies/` and source labels, canonical policy IR, confirmed contracts, and corrected semantics for development/corrected-control benchmarks.

## Paths prohibited

- Do not edit shared domain contracts/protocols, API/core/workflow, backend dependencies, fuzzing/evaluation internals, frontend, final submission source, or another person's evidence.
- Do not access private blind policy or labels before reveal and do not author blind extraction/fuzz results.

## Public inputs and outputs

- Consume `app.domain.models`, `app.domain.protocols`, and the public LLM protocol.
- Produce normalized policy documents, validated model output, exact cited extraction, compiled baseline rules/invariant suggestions, minimal revision proposals, and unverified draft wording.

## Ordered tasks

1. Task 12 — Safe text ingestion and typed model-output repair.
2. Task 13 — Cited rule extraction with validated provenance.
3. Task 14 — Policy compilation and intent-invariant suggestions.
4. Task 15 — Minimal revision proposal and unverified wording.
5. Task 21 responsibilities — synthetic development/corrected policy text plus source labels, canonical policy IR, confirmed contract, and corrected semantics.

## Required tests

- Cover size/character boundaries, prompt delimiting, one repair maximum, exact quote/span/hash validation, unsupported clauses, compiler limits, provenance, accepted-finding anchors, and 1–3 revision operations.
- Use deterministic fakes; never call a live provider or assert a model-authored oracle.

## Definition of done

- Every executable baseline rule has valid exact citation provenance, unsupported language is preserved, structured output validates against public contracts, tests pass, and owned synthetic corpus files meet the benchmark contract.

## Handoff evidence

- Begin only after the applicable custody gates and public-contract freeze. Record public inputs/outputs, commits, files, focused/full test commands, corpus hashes, repair/citation limitations, and downstream integration notes in `HANDOFF.md`.
