# PolicyFuzz interface

React/Vite implements the four public workflow views: input and contract, run evidence, findings and revision, and comparison. All server fields come from generated OpenAPI types and successful responses are validated against the public JSON schemas.

## Run the available mock workflow

From this directory:

```bash
npm ci
```

Create `.env.local` containing:

```dotenv
VITE_DATA_MODE=mock
```

Then run:

```bash
npm run dev
```

Choose the bundled sample, acknowledge the displayed rules and intent invariants, then confirm the contract. For the included revision example, reject the approval-gap finding and accept the cap-assertion finding; then confirm or reject the structured revision. Other finding selections end without a supported authored revision. The completed example demonstrates a revision that fails its safeguards. The mock uses authored synthetic display fixtures; it does not analyze pasted text or provide measured model/engine results.

## Public HTTP integration

HTTP is the default. Remove the mock setting or use `VITE_DATA_MODE=http`. The development proxy sends `/api` to `http://127.0.0.1:8000`; `VITE_API_BASE_URL` can select another public API origin. Never put a provider key in a frontend environment variable.

The client implements the declared `/api/v1` routes, with generated requests, runtime response validation, a 15-second request timeout, cancellation, and non-overlapping 1,500 ms polling during active stages. Confirmation and terminal stages pause polling. A successful action is followed by a fresh GET. Deletion uses the server's validated response before clearing the run.

**Live acceptance is pending Person 1's Task 20 API and coordinator.** A running legacy engine does not satisfy this public API dependency. The interface can be tested now using mock mode and fake HTTP tests.

## Checks

```bash
npm run generate:types
npm run check:generated
npm run typecheck
npm run test:run
npm run build
```

`generate:types` reads `../contracts/openapi.json`; shared schemas and the canonical fixture remain owned by Person 1. Commit the generated client after a reviewed contract change. `check:generated` detects drift. Tests use local fixtures and fake HTTP and never call a model provider.

See [INTEGRATION.md](INTEGRATION.md) for exact endpoints, public-data limits, and the remaining acceptance gates.
