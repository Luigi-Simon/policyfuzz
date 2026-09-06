# Frontend ↔ engine integration check

Date: 2026-09-06  
Frontend: `/Users/a123/Desktop/policyfuzz/policyfuzz/frontend`  
Engine: `/Users/a123/Desktop/policyfuzz/policyfuzz/engine`

## Verdict

**Architecture (agreed):** Frontend → Person 1 `backend` `/api/v1` → engine sidecar `/v1`. Do **not** wire the UI straight to `engine/`.

**Fit today:** Frontend is still a mock shell. Engine works. Person 3 shipped `HttpPolicyEngineClient` under `backend/app/features/fuzzing/` for Person 1 to call — see `PERSON1_ORCHESTRATION.md` and `team/person-3-fuzzing/HANDOFF.md`.

## What was tested

### Frontend code inspection
- No `fetch` / `axios` / `src/api/` transport
- No `import.meta.env.VITE_*` usage
- `VITE_DATA_MODE` / `VITE_API_BASE_URL` exist only in root `.env.example` (aspirational)
- Screens use local `preview.ts` / `behavior.tsx` state + timers

### Engine live smoke (port 8000)
- `GET /health` → OK
- `POST /v1/runs` (policy text + `audience_json`) → OK (`RunRecord` + score)
- `GET /v1/runs/{id}`, `/effectiveness`, `/evaluation`, `/ir`, `/v1/contracts` → OK
- `POST /v1/runs/{id}/revise` → OK
- Planned frontend paths below → **404**

## Fit matrix

| Frontend plan (INTEGRATION.md) | Engine today | Fit? |
|---|---|---|
| `POST /api/v1/runs` | `POST /v1/runs` | Path prefix mismatch |
| `GET /api/v1/runs/{id}` → `RunView` | `GET /v1/runs/{id}` → `RunRecord` | Different response model |
| `POST …/confirm-contract` | *(none)* — closest: create already compiles IR | Missing |
| `POST …/select-findings` | *(none)* — have `/evaluation` + `/effectiveness` | Missing |
| `POST …/confirm-revision` | `POST …/revise` `{instruction}` | Different semantics |
| `DELETE …/runs/{id}` | *(none)* | Missing |
| `GET /api/v1/health` | `GET /health` | Path mismatch |
| Poll every 1.5s for stages | Create is **synchronous** (`completed` when returned) | Different lifecycle |
| Audience goals/groups/assumptions in RunView | `SeedSpec` + `audience_json` segments | Partial / different shape |
| Optional simulation | `POST …/rehearse?swarm=true` | Exists, but not in frontend plan |

## Other integration gaps

1. **Two backends in the repo**  
   - `backend/` = PolicyFuzz Person 1 scaffold (frontend’s intended long-term target)  
   - `engine/` = this rehearsal API (Person 3 working copy)  
   Frontend docs aim at Person 1’s `/api/v1` surface, not `engine/`.

2. **CORS**  
   Engine allows `localhost:5173` and `3000`. Fine once HTTP is wired. Vite currently has **no proxy** to 8000.

3. **Auth / secrets**  
   Neither side requires auth. Do not commit `.env`; engine `.env.example` is enough.

4. **Data mode**  
   Root `.env.example` says `VITE_DATA_MODE=mock`. Until Task 22/23 HTTP transport lands, live engine cannot be exercised from the UI.

5. **Product vocabulary**  
   Frontend: interpretation → findings → revision → comparison (`RunView`).  
   Engine: IR → fuzz suite → evaluation → effectiveness → optional revise/rehearse.  
   Needs an adapter or Person 1 orchestration layer — not a 1:1 rename.

## Minimal path (Person 1 orchestration)

1. ~~Decide architecture~~ → **Person 1 owns public API; engine stays behind it.**
2. Person 1: wire workflow to `HttpPolicyEngineClient` / `RehearsalRequest`.
3. Person 1: freeze OpenAPI `RunView` and map engine DTOs → public responses.
4. Frontend: HTTP transport to `/api/v1` only; keep `VITE_DATA_MODE=mock` until contracts freeze.
5. Deploy engine as localhost/sidecar; do not put engine URLs in `VITE_API_BASE_URL`.

## Commands to re-verify engine alone

```bash
cd engine
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
# docs: http://127.0.0.1:8000/docs
# pack: http://127.0.0.1:8000/download/api-docs.zip
```
