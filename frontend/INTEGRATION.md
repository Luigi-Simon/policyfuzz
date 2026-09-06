# Frontend integration boundary

## Current behavior

Mock mode is the default and is the mode used by the component tests. It renders the complete four-screen interaction with illustrative local data and does not send policy text to a server.

Setting `VITE_DATA_MODE=http` opts into a temporary, direct adapter to the checked-in engine sidecar. This path consumes the engine's `RunRecord` shape from `engine/app/contracts/` and calls `/v1` directly. It does not represent a frozen PolicyFuzz public contract.

| UI action | Current HTTP behavior |
|---|---|
| Analyze policy / use sample | `POST /v1/runs` as multipart form data |
| Confirm contract | Uses the synchronous create result; optionally calls `POST /v1/runs/{id}/rehearse?swarm=true` |
| Finding accept/reject/clarify | Browser state only; no server decision is recorded |
| Confirm revision | Sends accepted finding summaries and intent text as the `instruction` to `POST /v1/runs/{id}/revise` |
| Clear view | Cancels the active browser request and resets local state; server data remains |

Engine create, rehearse, and revise are synchronous endpoints. The frontend therefore waits for one bounded request and does not poll. Each request has a two-minute timeout, accepts a caller `AbortSignal`, and ignores a completion after reset or a newer request.

Successful responses receive handwritten runtime validation before mapping. The validator checks the allowed engine run statuses and validates every nested field consumed by `mapRunToView`, including policy rules/citations/conditions/obligations, scenario kinds and facts, finding verdicts and traces, recommendation actions, booleans, arrays, objects, and finite integer scores/revisions. Invalid JSON or an incompatible response is shown as a concise public error; raw backend bodies remain available only on the internal error object.

## UI data boundary

- `src/api/types.ts` describes only the subset of the engine `RunRecord` used by this temporary adapter.
- `src/api/engineClient.ts` owns `/v1` requests, cancellation, timeout, validation, and concise error translation.
- `src/api/mapRun.ts` projects a validated engine record into frontend display shapes.
- `src/preview.ts` and static content in `src/behavior.tsx` are illustrative mock data, not backend models or benchmark evidence.
- HTTP finding decisions are labelled local. The engine has no finding-decision endpoint.
- HTTP clear is labelled **Clear view**. The engine has no run deletion endpoint.

The UI does not claim that its display `RunView` is the planned public `RunView`. No backend module is imported by the frontend.

## Pending integration dependencies

Person 1 still needs to provide and freeze:

1. The public `/api/v1` orchestration surface and its public error rules.
2. A versioned public `RunView` schema with stage, confirmation, terminal, and partial-result semantics.
3. Generated TypeScript types/client configuration and a canonical completed fixture.
4. Commands and concurrency rules for interpretation confirmation, finding decisions, revision confirmation, and deletion or retention.
5. If orchestration is asynchronous, snapshot/polling semantics: allowed active states, interval, overall deadline, retry/backoff rules, cancellation, stale-write protection, and terminal errors.
6. Stable identifiers and provenance linking policies, rules, scenarios, actions, evaluations, findings, revisions, and comparisons.
7. Immutable comparison inputs and backend acceptance results for fixed-action and behavioral comparison views.
8. Public redaction rules for uploaded policy content, source quotations, provider errors, prompts, and stored artifacts.

Until those dependencies exist, keep the direct engine adapter explicit and opt-in. Do not invent `/api/v1` endpoints, treat the handwritten types as generated public types, persist local finding choices by implication, or add artificial polling to the synchronous engine.

## Fixture needs for the future public contract

The frozen contract should include examples for a normal completed run, a stage in progress, a public error, an unsupported interpretation, no reviewable findings, clarification pending, revision rejected, failed safeguards, changed comparison inputs, an additional-scenario cohort, cancellation, expiration, and deletion/retention behavior.

One complete fixture should link policy → confirmed intent → scenario → evaluated action → finding → revision → fixed-action comparison using stable public IDs and source-bearing evidence.
