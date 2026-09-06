# PolicyFuzz interface

React/Vite implementation of the supplied four-screen workflow. The default mode is a local mock preview with explicitly illustrative policy, findings, scores, and comparison states.

## Run the mock preview

From this directory:

```bash
npm ci
npm run dev
```

Choose **Use sample policy**, review and confirm the interpretation, inspect scenarios, decide each finding, prepare a revision, and open the comparison. Arbitrary pasted policy text is not analyzed in mock mode.

## Temporary engine HTTP adapter

HTTP mode is an explicit development option for the engine sidecar in `../engine`; it is not the planned public PolicyFuzz API.

1. Start the engine from `engine/` on port 8000.
2. Copy `.env.example` to `.env` and set `VITE_DATA_MODE=http`.
3. Leave `VITE_API_BASE_URL` empty to use the Vite proxy, or set an engine base URL.
4. Run `npm run dev`.

The adapter currently calls these engine endpoints:

- `POST /v1/runs` to synchronously ingest, extract, generate scenarios, evaluate, and score.
- `POST /v1/runs/{run_id}/rehearse?swarm=true` when optional simulation is enabled.
- `POST /v1/runs/{run_id}/revise` to synchronously revise and rerun the engine pipeline.

Requests have a fixed two-minute client timeout and are cancelled when the browser view is reset or superseded. Responses are checked at runtime against the engine `RunRecord` fields consumed by the UI, including nested rules, scenarios, findings, traces, status values, and numeric values.

The engine has no delete endpoint. **Clear view** resets browser state and leaves server run data in the engine store. Finding accept/reject/clarification choices remain local; accepted items are sent only as prose in a later `/revise` instruction.

## Checks

```bash
npm run typecheck
npm run test:run
npm run build
```

Tests use local fixtures and mocked HTTP only. They never call a provider or a live engine.

## Integration status

This checkout has no frozen public `RunView`, public `/api/v1` orchestration API, generated API client, canonical completed fixture, or agreed decision/delete commands. `src/api/engineClient.ts` and `src/api/types.ts` are handwritten temporary engine adapters. `src/preview.ts` and the mock behavioral content remain UI-only illustrative data.

Do not add polling around the current engine create/revise calls: those endpoints return synchronously. Polling belongs with a future public asynchronous orchestration contract once its stages, snapshot schema, terminal states, timing limits, and error semantics are frozen.

See [INTEGRATION.md](INTEGRATION.md) for the remaining dependencies and exact boundary.
