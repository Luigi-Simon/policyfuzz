# Policy rehearsal engine

FastAPI backend that turns a policy PDF into compiled **PolicyIR**, then Person 3 fuzzes it (max 50 agents), grades the suite, optionally runs the MiroFish swarm, and returns a 0–100 effectiveness score.

This is **not** the MiroFish UI. MiroFish stays next door as the optional swarm simulator.

| Role | Owns | This repo |
|------|------|-----------|
| 1 Integration | contracts, routes, coordinator, run state, LLM adapter, CI | implemented |
| 2 Policy intelligence | PDF ingest, cited rules, revise + recompile | implemented |
| 3 Fuzz + swarm + score | `PolicyIR → ≤50 agents → EvaluationReport + PolicyEffectivenessReport` | implemented |
| 4 Custom grader | optional `EVALUATOR=` override | plugin slot |
| 5 Product / demo | React | CORS + OpenAPI + `/v1/contracts` |

## Run

```bash
cd engine
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # optional: add LLM_API_KEY for better extraction
uvicorn app.main:app --reload --port 8000
```

- API: http://localhost:8000/docs
- Downloadable pack for the frontend: http://localhost:8000/download/api-docs.zip
- Also in the repo: `docs/API.md`, `docs/openapi.json`, `docs/swagger.html`

Without `LLM_API_KEY`, extraction uses a deterministic heuristic (must/shall/may/should sentences + citations). Good enough to unblock you and CI. With a key, the same OpenAI-compatible adapter MiroFish uses compiles a richer IR.

## Pipeline

```
policy PDF/text + audience seed/segments + N
    → P2 PolicyIR
    → P3 fuzz agents (capped at 50)
         ├─ EvaluationReport           (pass / fail / traces → P2 repair)
         └─ MiroFish swarm (optional)  (agents talk to each other)
    → PolicyEffectivenessReport        (score 0–100, justification, next actions)
```

`POST /v1/runs` is **synchronous**. It compiles IR, generates ≤50 fuzz agents, grades them, and writes a **preview score** from the fuzzer. It does **not** wait for a live swarm. Audience is injectable via `seed_text` / `seed_file` / `groups` / `audience_json` + optional `locale` — not hardcoded to any jurisdiction.

```
GET  /v1/runs/{id}/effectiveness     # score + justification + recommended_actions
GET  /v1/runs/{id}/evaluation        # per-agent pass/fail traces for Person 2
GET  /v1/runs/{id}/mirofish          # JSON pack
GET  /v1/runs/{id}/mirofish/seed.md  # upload this in the MiroFish UI
POST /v1/runs/{id}/rehearse?swarm=true
POST /v1/runs/{id}/revise            # iteration round from recommended_actions / custom instruction
GET  /v1/contracts                   # JSON Schema for TS types (includes AudienceSegment)
```

Swarm scoring needs MiroFish at `http://localhost:5001` and `MIROFISH_BASE_URL=http://localhost:5001`. Without that, rehearse still returns a fuzz-only score. GST voucher is only a sample policy, not hardcoded logic.

## Person 3

Built-in `FuzzDesigner` + `RuleEvaluator` run on every create/revise. Population is capped at `MAX_SWARM_AGENTS=50`.

Frontend (Person 1) later uploads:

1. The policy / scenario PDF (`file`)
2. The audience seed (`seed_text` and/or `seed_file`)

Person 2 hands off a revised PolicyIR (`POST /v1/runs/{id}/revise`). Person 3 fuzzes that IR.

Results on `GET /v1/runs/{id}/effectiveness`:

- `score` 0–100
- `justification` — fuzz summary plus named swarm posts when the swarm ran
- `highlights` — significant agent interactions
- `recommended_actions` — smallest useful edits for Person 2's repair agent

Override plugins only if you replace the implementation:

```
SCENARIO_DESIGNER=app.services.fuzz:FuzzDesigner
EVALUATOR=app.services.evaluate:RuleEvaluator
```

## Frontend (role 5)

Multipart create:

```
POST /v1/runs
file: <policy pdf>
seed_file: <optional audience pdf>
seed_text: "personalities / census notes"
population_size: 50
groups: "students,teachers,parents"
```

Then:

- `GET /v1/runs/{id}` — full run (document, IR, suite, score)
- `GET /v1/runs/{id}/effectiveness` — 0–100 + justification
- `POST /v1/runs/{id}/revise` `{"instruction": "Exempt grade 12"}` — recompile IR, regenerate agents
- `POST /v1/runs/{id}/rehearse?swarm=true` — run MiroFish and rescore
- `GET /v1/contracts` — generate TypeScript types

CORS defaults to `localhost:5173` and `localhost:3000`.

## Tests / CI

```bash
LLM_MOCK=true pytest -q
```

GitHub workflow: `.github/workflows/ci.yml`. Init git in `engine/` (or make `engine/` the repo root) so that workflow is picked up.

## Layout

```
app/contracts/     shared pydantic models — source of truth
app/services/      ingest, extract, fuzz, evaluate, swarm, score
app/plugins/       ScenarioDesigner + Evaluator ABCs
app/api/routes.py  FastAPI
app/llm.py         OpenAI-compatible adapter
app/store.py       data/runs/{id}/run.json + policy_ir.json
examples/          sample policies (GST voucher is a fixture, not the fuzzer)
```
