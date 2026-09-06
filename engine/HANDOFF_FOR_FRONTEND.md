# Engine handoff (sidecar)

This folder is the Policy Rehearsal FastAPI engine. It is **not** the public frontend API.

**Long-term wiring:** Frontend → Person 1 `backend` `/api/v1` → this engine `/v1` via `HttpPolicyEngineClient` (`backend/app/features/fuzzing/`).

See `PERSON1_ORCHESTRATION.md` and `team/person-3-fuzzing/HANDOFF.md`.

## Start (sidecar)

```bash
cd engine
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # add LLM key only if you want richer extraction
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Frontend

Point `VITE_API_BASE_URL` at **Person 1 backend**, not this engine. Keep `VITE_DATA_MODE=mock` until Person 1 freezes contracts.

Engine docs (for Person 1 / adapters only):

- Live: http://127.0.0.1:8000/docs
- Pack: http://127.0.0.1:8000/download/api-docs.zip
- Repo: `docs/API.md`, `docs/openapi.json`, `docs/contracts.json`

## Important endpoints

| Action | Endpoint |
|--------|----------|
| Create run (any policy + audience) | `POST /v1/runs` |
| Snapshot | `GET /v1/runs/{run_id}` |
| Effectiveness score | `GET /v1/runs/{run_id}/effectiveness` |
| Evaluation traces | `GET /v1/runs/{run_id}/evaluation` |
| Revise / iterate | `POST /v1/runs/{run_id}/revise` |
| Optional swarm | `POST /v1/runs/{run_id}/rehearse?swarm=true` |
| Schemas | `GET /v1/contracts` |

Audience injection fields on create: `seed_text`, `seed_file`, `groups`, `audience_json`, `locale`, `population_size`.

Note: this engine uses `/v1/...`. Frontend should call Person 1 `/api/v1/...` only; Person 1 maps to this client.
