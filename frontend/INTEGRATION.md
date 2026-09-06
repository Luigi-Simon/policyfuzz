# Public workflow integration

## Shared surface

The frontend consumes the public `RunView` through generated TypeScript aliases. Ajv validates snapshots against `contracts/jsonschema/RunView.schema.json`; request/response names are generated from `contracts/openapi.json`. The exported models are available now; the final version 1.0 freeze follows Person 1's Task 4.

| Action | Declared wire contract |
| --- | --- |
| Create | `POST /api/v1/runs` → `202 CreateRunResponse`, then GET |
| Load / poll | `GET /api/v1/runs/{run_id}` → `200 RunView` |
| Confirm or reject contract | `POST .../confirm-contract` → `200 RunView`, then GET |
| Submit finding decisions | `POST .../select-findings` → `200 RunView`, then GET |
| Confirm or reject revision | `POST .../confirm-revision` → `200 RunView`, then GET |
| Delete | `DELETE /api/v1/runs/{run_id}` → `200 DeleteRunResponse` |

The bundled sample control submits `sample_id: "development-policy"`, matching the registered backend sample ID. The current cached backend loads the recorded public run and returns a completed `RunView`; it makes no provider call.

Errors use `{error: PublicError}`. A 409 response is followed by a fresh GET because the current error schema does not carry stage/actions. Unknown or malformed responses become concise public errors. A run ID is checked against the requested run before applying a response.

## Lifecycle and evidence

Server stage and allowed actions control progression. Active stages poll after the previous GET settles; review and terminal stages stop polling. In-flight work is aborted on unmount or replacement, and stale completions cannot overwrite a newer run. Earlier public snapshots may be retained within the current browser session for back-navigation. Missing historical details on a directly loaded later run remain unavailable.

Mock provenance is explicit: the canonical completed fixture is authored synthetic display data and demonstrates a rejected patch. It is not the recorded cached-run deliverable. HTTP responses display their actual `live` or `cached` mode. A transport label is separate from run provenance. In cached mode, create immediately loads the completed public record; the only allowed action is deletion.

Finding decisions use stable IDs and the reviewable IDs supplied by the server. Structured revision operations and the server's acceptance flags determine the result; drafted wording remains labelled unverified. The frontend does not create findings, scores, oracle answers, or pass/fail verdicts.

## Public projection gaps for Person 1

These are pending upstream fields, not permission to read backend internals or synthesize evidence.

| Planned detail | Current public data | Follow-up |
| --- | --- | --- |
| Scenario facts and individual assertion results | Visible trace IDs, facts, predicates, resolved effects, compliance, citations and hashes; aggregate assertion counts | Add only capture-safe assertion detail if final footage requires it; preserve holdout redaction. |
| Measured adaptation lift / cycle count | Current covered/total counters and stage events; current cached record's `targeted_cycles: 0` is not a dedicated `RunView` field | Add a public cycle-count/lift projection only if the final UI must display it. Do not stage an adaptive cycle when the recorded suite already satisfies minimum coverage. |
| Fixed / remaining / regressed item IDs | Aggregate assertion transitions, acceptance counts, and visible trace summaries | Add visible-only ID collections only if required by the final capture. |
| Engine version | Full engine SHA-256 in comparison inputs | Expose the version string separately; the UI labels the current value as a hash. |
| Completed-run rule and proposal history | Pending-confirmation data only | Add a safe historical projection if direct reload must retain those details. |

## Remaining acceptance gates

1. Keep the frozen public contract and generated client synchronized; `npm run check:generated` currently passes.
2. The same-process real-TCP cached smoke now passes create, GET, completed comparison, patch acceptance, `200` deletion, and subsequent `404`. This is API evidence, not browser evidence.
3. Complete live-mode confirmation/rejection behavior only in an approved environment with a configured provider; the current rehearsal uses four scripted responses and zero actual provider calls.
4. Verify keyboard navigation and the 375 px / 1440 px layouts in a browser binary that shares the FastAPI/Vite network namespace. `submission/evidence/browser-rehearsal.md` records why the available cloud/local attempts could not load a page; no visual acceptance or screenshot is claimed.
5. Freeze the verified executable and actual evidence before final deck screenshots or video capture.

The private benchmark lineage is selected by `submission/evidence/active-benchmark.json`. It is schema-validated, agent-authored and late-sealed, with human review pending and headline gold scoring disabled. No private benchmark content is a frontend fixture.
