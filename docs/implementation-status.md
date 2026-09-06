# Implementation and release status

This is the execution status for the 25-task approved plan. Implementation and
verification are distinct from human benchmark approval and final submission.
The version `1.0` domain models and HTTP contracts remain authoritative where
examples in the older plan differ.

| Task | Owner | Deliverable | Status |
|---|---|---|---|
| 1 | P1 | Repository and scoped `AGENTS.md` work packets | Implemented |
| 2 | P1 | Pydantic contracts | Implemented and frozen |
| 3 | P1 | Canonical hashes, artifacts, 111 schemas and OpenAPI | Implemented |
| 4 | P1 | Protocols, typed LLM contracts, adapters and fake client | Implemented and frozen |
| 5 | P4 | Predicate execution and rule validation | Implemented |
| 6 | P4 | Effect resolution, overrides and compliance | Implemented |
| 7 | P4 | Assertions, traces and deterministic execution | Implemented |
| 8 | P3 | Mechanical scenarios and boundaries | Implemented and verified |
| 9 | P3 | Exploratory generation without model-owned answers | Implemented and verified |
| 10 | P3 | Validation, deduplication and stable IDs | Implemented and verified |
| 11 | P3 | Coverage, one adaptive cycle and suite freeze | Implemented and verified |
| 12 | P2 | Ingestion and bounded typed-output repair | Implemented and verified |
| 13 | P2 | Extraction and exact citations | Implemented and verified |
| 14 | P2 | Compilation and provisional invariant suggestions | Implemented and verified |
| 15 | P2 | Structured proposal and unverified wording | Implemented and verified |
| 16 | P4 | Evidence-backed findings and grouping | Implemented |
| 17 | P4 | Atomic structured revision | Implemented |
| 18 | P4 | Regression, seven acceptance checks and metrics | Implemented |
| 19 | P1 | Run store, coordinator and public projection | Implemented |
| 20 | P1 | FastAPI, dependency wiring and safe errors | Implemented and verified |
| 21 | Shared | Synthetic corpus, recorded demo, benchmark tools and custody | Tools/corpus implemented; human and blind-result gates pending |
| 22 | P5 | Typed React workflow and four views | Implemented |
| 23 | P5 | HTTP transport and bounded polling | Implemented; real HTTP verified, browser acceptance pending |
| 24 | P5 | Nine-slide deck, narration, captions and final video | Draft sources prepared; final capture/reviews pending |
| 25 | P1 | README, CI, reproducibility, package and GitHub | Tools implemented and verified; final release pending |

## Verified application checks

- Backend: **1,438 tests passed**; Ruff check/format passed for 162 Python files.
- Frontend: **108 tests passed**; generated-type drift, type checking and production build passed.
- Shared scripts: 13 files passed Ruff check/format; caption generator: two tests passed.
- Contracts: all **111 schemas**, OpenAPI and the canonical view fixture match generated output.
- Actual TCP API create/read/completed replay/delete checks passed within the backend suite.
- Current engine replay: **three identical executions**; development/control labels verify independently.
- Draft PDF: **nine pages**. Final submission checks intentionally reject absent final media and evidence.

The machine-readable application verification record is
[`implementation-verification.json`](../team/person-1-integration/evidence/implementation-verification.json).
It is explicitly separate from Gate B and final submission approval.

## Evidence and limits

The development demonstration executes the real compiler, planner, evaluator,
revision validator and comparison workflow with explicit scripted model responses.
It currently exercises ten scenarios and three seeded defects. A successful
structured revision removes those three defects and passes all seven checks on
the same frozen suite. There are no live provider calls in this demonstration.
Coverage is already sufficient, so this particular recording has no targeted
cycle; separate tests exercise that branch.

The authored development/control benchmark suites contain 15 cases each and
independent synthetic labels. They are separate from the generated ten-case demo
suite. `scripts/verify_benchmarks.py` re-executes them and verifies their saved
technical scores without rewriting labels. These are not human-reviewed or blind
performance claims.

The strict benchmark scorer requires the same contract and authored gold scenario
identities. A normal workflow generates different scenario identities, so passing
a raw workflow result to that scorer does not automatically measure first-run
discovery recall. A separately labelled post-run gold-assisted assessment may
evaluate a captured policy on revealed gold cases. It cannot replace the original
run or satisfy the headline discovery gate. That metric remains unmeasured until
an independently verified reconciliation procedure is supplied.

## Remaining release gates

1. Verify the app in an actual browser, including both requested viewport widths,
   keyboard operation and complete live interaction. The real TCP API check is
   recorded separately; it does not stand in for browser acceptance.
2. An independent human must review the sealed benchmark's semantics and publish
   a hash-bound approval record. Preserve the historical late-seal provenance.
3. Perform the two actual independent ten-minute reviews and the authorized
   one-shot blind run. Preserve failures and original evidence. Resolve the
   first-run discovery measurement limitation before claiming its threshold.
4. Pass Gate B, create the clean annotated application tag, wait the required six
   real hours, capture final media and obtain the prescribed human reviews.
5. Produce the final nine-page PDF, video and captions; verify and package them
   at the final tag, then publish the release. Drafts do not satisfy these gates.

Live-provider acceptance is also pending because this workspace has no configured model/key.

The application can be developed and rehearsed now. Pending evidence has not been
replaced with invented approvals, a final release tag, or simulated footage.
