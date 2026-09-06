# Person 1 — orchestrating the rehearsal engine

**Decision:** Frontend talks only to Person 1 `backend` at `/api/v1`. This `engine/` process stays behind that API as a sidecar.

## Run the sidecar

```bash
cd engine
cp .env.example .env   # add LLM keys only if you need swarm / LLM paths
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # or project install instructions
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- Health: `GET http://127.0.0.1:8000/health`
- Docs: `http://127.0.0.1:8000/docs`
- Paths are **`/v1/...`**, not `/api/v1`

## Call it from PolicyFuzz backend

Use the Person 3 client (do not call `engine` URLs from the frontend):

```python
from app.features.fuzzing import HttpPolicyEngineClient, RehearsalRequest

client = HttpPolicyEngineClient()  # POLICY_ENGINE_BASE_URL
result = client.create_rehearsal(RehearsalRequest(policy_text=...))
```

See `team/person-3-fuzzing/HANDOFF.md` for the full mapping table and error codes.

## What Person 1 still owns

1. Public FastAPI routes matching frontend `INTEGRATION.md` / OpenAPI.
2. Mapping engine `RehearsalResult` → frozen `RunView`.
3. Async run lifecycle (engine create is sync today).
4. Adding `POLICY_ENGINE_BASE_URL` to root `.env.example` and promoting `httpx` to main deps if needed.
5. CORS / auth for the **public** API only; engine can stay localhost-only in deploy.
