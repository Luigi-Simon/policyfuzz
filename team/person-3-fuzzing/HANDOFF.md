# Person 3 — Fuzzing / engine sidecar handoff

Status: Ready for Person 1 orchestration wiring (client + tests landed).

## Architecture decision (agreed)

```
Frontend  →  Person 1 backend `/api/v1/...`  →  engine sidecar `/v1/...`
```

- Person 1 owns the public API, OpenAPI/`RunView`, async lifecycle, and workflow.
- The rehearsal engine stays a **sidecar** (`engine/` or separate deploy). Do **not** expose it to the frontend.
- Person 3 provides an HTTP adapter under `backend/app/features/fuzzing/` so workflow can call the engine without knowing FastAPI details.

## Interfaces Person 1 should call

```python
from app.features.fuzzing import (
    AudienceSegmentInput,
    HttpPolicyEngineClient,
    RehearsalRequest,
)

with HttpPolicyEngineClient() as engine:  # POLICY_ENGINE_BASE_URL
    result = engine.create_rehearsal(
        RehearsalRequest(
            policy_text=policy,
            seed_text=seed,
            population_size=20,
            locale="en-US",
            groups=("students", "teachers"),
            segments=(
                AudienceSegmentInput(id="students", weight=0.6),
                AudienceSegmentInput(id="teachers", weight=0.4),
            ),
        )
    )
    # result.engine_run_id, result.score, result.effectiveness, ...
    revised = engine.revise(result.engine_run_id, instruction="Clarify storage.")
```

Protocol: `PolicyEngineClient` (same module) — inject a fake in workflow tests.

Errors: `EngineClientError` with stable `.code` values:
`ENGINE_EMPTY_POLICY`, `ENGINE_EMPTY_INSTRUCTION`, `ENGINE_HEALTH_FAILED`,
`ENGINE_CREATE_FAILED`, `ENGINE_GET_FAILED`, `ENGINE_EFFECTIVENESS_FAILED`,
`ENGINE_REVISE_FAILED`.

## Suggested Person 1 mapping (FE plan → engine)

| Public `/api/v1` (Person 1) | Engine op via this client |
|---|---|
| Create run / start interpretation | `create_rehearsal` → store `engine_run_id` on run |
| Poll / stages | Person 1 owns async; engine create is **sync** today — wrap or background job |
| Effectiveness / findings | `get_effectiveness` / `get_rehearsal` |
| Confirm revision | `revise(engine_run_id, instruction)` |
| Health | Person 1 health + optional `engine.health()` |

Do **not** proxy engine paths 1:1 under `/api/v1`. Map into frozen `RunView`.

## Files

| Path | Role |
|---|---|
| `backend/app/features/fuzzing/engine_client.py` | HTTP client + `PolicyEngineClient` protocol |
| `backend/app/features/fuzzing/types.py` | Feature DTOs (not domain models) |
| `backend/app/features/fuzzing/__init__.py` | Public exports |
| `backend/tests/features/fuzzing/test_engine_client.py` | MockTransport tests (no live LLM) |
| `engine/` | Runnable sidecar (Person 3 working copy; relocate if you prefer) |
| `engine/PERSON1_ORCHESTRATION.md` | Sidecar run + env notes |

## Env (Person 1 should add to root `.env.example`)

```
POLICY_ENGINE_BASE_URL=http://127.0.0.1:8000
```

Optional: move `httpx` from `[project.optional-dependencies] dev` into main `dependencies` when the API process always talks to the engine (Person 3 cannot edit root deps).

## Commands

```bash
# Sidecar
cd engine && uvicorn app.main:app --host 127.0.0.1 --port 8000

# Client unit tests (mocked HTTP)
cd backend && uv run --extra dev pytest tests/features/fuzzing/test_engine_client.py -q
```

## Submission evidence

- Focused tests: mocked create / effectiveness / revise / error mapping.
- No live provider calls from these tests.

## Limitations

- Mechanical scenario suite / coverage freeze (Tasks 8–11) still pending; this handoff is the **engine adapter** only.
- Engine create is synchronous; Person 1 must own FE-facing poll stages.
- Domain models / `app.domain.protocols` not frozen yet — lift `PolicyEngineClient` there when ready.
- Do not commit engine `.env` with API keys.
