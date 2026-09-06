# Architecture evidence boundary

**Status: DRAFT — target architecture documented; integrated `demo-core-v1` evidence pending.**

## Approved target

PolicyFuzz is designed as a contract-first modular monolith. A React/Vite client consumes the public `RunView` API from FastAPI. The coordinator invokes separate policy interpretation, fuzz generation, and deterministic evaluation stages while exposing only display-safe state.

The intended trust boundary is explicit:

| Model-backed stage | Deterministic Python authority |
| --- | --- |
| Interpret policy language into proposed structured rules | Validate schemas, identifiers, citations, hashes, and frozen anchors |
| Generate bounded initial and targeted scenarios | Execute assertions and assign outcome states |
| Draft one proposed revision after human finding decisions | Apply only session-confirmed edits and reject invalid patches |
| Supply suggestions that remain reviewable | Compute metrics, compare the identical frozen suite, and decide all seven acceptance gates |

The seven planned patch-acceptance gates are: matching suite hash; every target finding fixed; no new failure outside targets; no protected-case regression; no new `GAP`, `CONFLICT`, `INCONCLUSIVE`, or `ERROR`; unchanged unrelated rule signatures; and no worse holdout result. These are approved design requirements, not completed-run results.

## Current evidence state

- The integrated backend, public UI, and `demo-core-v1` tag are not present in this work packet, so no current screenshot or successful end-to-end run is asserted here.
- Gate B evidence at `team/person-1-integration/evidence/gate-b-verification.json` is a required final dependency and is currently unavailable.
- The public benchmark-v2 metadata records successful schema and archive integrity checks. It also records agent authorship, sealing after development, pending independent human review, no engine/provider execution, and headline gold-scoring ineligibility.
- This document does not establish implementation conformance. Final architecture claims must cite the frozen code, Gate B report, and captured `demo-core-v1` build.

## Final evidence required

Before this document can be marked final, record the `demo-core-v1` commit, the frozen suite hash, the deterministic engine version, the Gate B artifact path and SHA-256, and capture locations that show the `RunView` boundary and mode labels. Any diagram or screenshot must be generated from that exact frozen build. Synthetic, live, cached, blind, and unverified labels remain visible wherever applicable.

The final evidence manifest uses code-owned Task 24 metric keys and exact structured provenance for data type, actual run mode, verification status, and blind eligibility. Each displayed metric binds its evidence value and provenance in one canonical claim token; a label list elsewhere cannot validate a claim, and a separate numeric value may not share the token's line. The verifier audits non-empty extracted deck text plus the mandatory final script and recomputes hashes inside the selected candidate root. Its public `enumerate_candidate_files(candidate_root)` function returns the deterministic root-relative member list used for size and duplicate-final-name checks. Task 25 must package that exact list and record a matching manifest; packaging acceptance remains pending until it does. Generic `raw`, `backup`, and `backups` directories remain candidates—the narrow exception covers only purpose-specific raw/backup video paths and files, alongside the documented development, dependency, cache, coverage, build, and distribution exclusions.
