# V2 first-run handoff

Branch: `p1/feat-v2-core`. Base: `786b6d70817064cc9ad1967475606a671c0e604e`.
PR target: `p1/feat-policyfuzz-v2`. Startup: [README](README.md#run-the-first-core-milestone).

## What is implemented

The `/v2` form sends four policy fields and an optional explicit fixture selector
to the standalone `POST /api/v2/runs` endpoint. The Orchestrator constructs a fresh
run/request identity, binds the exact policy description and full request hash,
calls `SandboxService`, validates the result and returns its public projection.

The screen displays fixture labels, complete/partial/failed/cancelled status,
participant counts, persona descriptions, English messages, translation labels,
reply links, source evidence, limitations and trace identifiers. A failed
translation remains a partial result with the exact English placeholder.

The Orchestrator Agent and fixture Sandbox Agent operate in this milestone.
Metric Agent and Judge Agent are listed as future stages. Parsing, translation,
validation and storage remain supporting tools, not additional agent roles.

## Public interface

```json
{
  "policy": {
    "title": "Synthetic transit pilot",
    "description": "Extend late-night service for a six-month pilot.",
    "agent_seed": "Practical, safety-focused and accessibility-focused voices.",
    "agent_count": 3
  },
  "fixture_name": "completed"
}
```

Use `partial_translation_unavailable` for the alternate sample. This selector is
a demo control, not a fifth policy input. Counts are integers from 1 to 100. Title,
description and seed must be nonblank; maximum lengths are 200, 50,000 and 2,000.
Titles must pass the current English display guard. Supporting documents are not
part of this first-run form. HTTP errors use fixed public English messages.

- API: `backend/app/v2/main.py`, `orchestrator.py`, `run_models.py`.
- Contract source: `run_models.py`; generated HTTP contracts: `contracts/v2-app/`.
- Existing Sandbox boundary: `app.v2.contracts` and `app.v2.protocols`, unchanged.
- Frontend: `frontend/src/v2/`; generated types: `api.generated.ts`.
- Integration: additive `/v2` entry and `/api/v2` proxy, `npm run dev:v2`.
- No new package dependencies. Existing backend/frontend dependencies are reused.

Regenerate the HTTP contracts from the repository root after an intentional API
change, then regenerate types:

```bash
backend/.venv/bin/python -m app.v2.export_api
npm --prefix frontend run generate:v2
```

## Friend's handoff remains independent

Friend continues on `p3/feat-v2-sandbox`, following
[the Sandbox handoff](../../team/v2-sandbox/HANDOFF.md). Their owned folders and
the shared Sandbox contract are unchanged. The core calls the existing
`SandboxService.run(SandboxRequest) -> SandboxResult` protocol through an injected
factory. The first-run endpoint intentionally accepts only fixture results.
Live integration will require an explicit core configuration/label change and
integration tests; never silently replace fixture evidence with live output.

## Limitations and next work

- Fixture dialogue is authored synthetic data. It does not analyse policy text or
  personality seeds and is not evidence of a real public response.
- No live MiroFish or automated translation is added. The existing display guard
  rejects Han script; it is not a comprehensive language detector.
- Requests are synchronous and bounded by a timeout. There is no database, run
  retrieval, polling or persistent history. Public responses omit originals,
  policy descriptions and personality seeds.
- Next: define one executable demo domain, add Metric case generation and
  deterministic assertions, then Judge reporting with evidence references.

## Verification

Provider calls are prohibited in these checks. Run from the repository root:

```bash
backend/.venv/bin/python scripts/check_v2_foundation.py
backend/.venv/bin/python -m app.v2.export_api --check
backend/.venv/bin/python -m pytest backend/tests -q
backend/.venv/bin/python -m ruff check backend/app backend/tests
backend/.venv/bin/python -m ruff format --check backend/app backend/tests
npm --prefix frontend run check:generated
npm --prefix frontend run typecheck
npm --prefix frontend run test:run
npm --prefix frontend run build
```

Completed verification evidence:

- The v2 foundation check passed all 21 checks, and the standalone API suite
  passed all 35 tests.
- The full backend suite passed 1,590 tests plus 2 subtests. The existing v1
  contract, replay, offline-smoke and benchmark checks also passed.
- The frontend suite initially passed 189 tests. After adding the final public
  evidence boundary cases, it passed all 206 tests; typecheck, production build
  and generated-artifact checks also passed.
- Real complete and partial API runs passed in Chromium. The v1 home navigation
  also passed. Desktop at 1,280 pixels and mobile at 390 pixels had no horizontal
  overflow and no page errors.
- Browser verification used a locally packaged Chromium and font configuration
  in the verification environment; it did not add an application dependency.

The final boundary fix affected no backend source, style or contract output, and
changed no rendering code. The backend suites and browser screenshots therefore
were not rerun for that fix.
