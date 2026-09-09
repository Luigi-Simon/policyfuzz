# Policy rehearsal engine

Optional FastAPI engine that compiles policy PDF/text into a provisional **PolicyIR**, generates up to 50 exploratory scenarios, and can capture MiroFish conversations. Its evidence is independent of the core PolicyFuzz frozen suite. A heuristic score is available only when expected outcomes exist; ordinary generated cases are unasserted and must display **Not scored**.

This is **not** the MiroFish UI. MiroFish stays next door as the optional swarm simulator.

| Role | Owns | This repo |
|------|------|-----------|
| 1 Integration | contracts, routes, coordinator, run state, LLM adapter, CI | implemented |
| 2 Policy intelligence | PDF ingest, cited provisional rules, structured revisions | implemented |
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
uvicorn app.main:app --reload --port 8001
```

- API: http://localhost:8001/docs
- Downloadable pack for the frontend: http://localhost:8001/download/api-docs.zip
- Also in the repo: `docs/API.md`, `docs/openapi.json`, `docs/swagger.html`

Without `LLM_API_KEY`, or with `LLM_MOCK=true`, extraction uses an explicitly unverified demo heuristic. Live extraction validates complete source quotations and fails visibly on malformed or unsupported output; it does not silently substitute the demo interpretation. Source text beyond 24,000 characters is rejected rather than truncated.

The engine reads `.env` from its working directory, unlike the core backend. Configure `LLM_API_KEY`, `LLM_MODEL_NAME` and optionally `LLM_BASE_URL` here. The core backend separately uses `OPENAI_API_KEY` and `LLM_MODEL`. Keep all credentials server-side and out of Git. From the repository root, `npm run dev -- --agents` starts the installed core, engine and frontend environments together. It does not start the separate MiroFish project.

## Pipeline

```
policy PDF/text + audience seed/segments + N
    → P2 PolicyIR
    → P3 fuzz agents (capped at 50)
         ├─ EvaluationReport           (pass / fail / traces → P2 repair)
         └─ MiroFish swarm (optional)  (agents talk to each other)
    → PolicyEffectivenessReport        (score 0–100, justification, next actions)
```

`POST /v1/runs` is **synchronous**. It compiles IR, generates ≤50 exploratory cases, evaluates supplied assertions, and records whether a heuristic score is available. Model-generated scenarios do not supply their own expected answers. Creating a run does not wait for a live swarm by default. Audience is injectable via `seed_text` / `seed_file` / `groups` / `audience_json` + optional `locale`.

```
GET  /v1/runs/{id}/effectiveness     # score + justification + recommended_actions
GET  /v1/runs/{id}/evaluation        # per-agent pass/fail traces for Person 2
GET  /v1/runs/{id}/mirofish          # JSON pack
GET  /v1/runs/{id}/mirofish/seed.md  # upload this in the MiroFish UI
POST /v1/runs/{id}/rehearse?swarm=true
POST /v1/runs/{id}/revise            # iteration round from recommended_actions / custom instruction
GET  /v1/contracts                   # JSON Schema for TS types (includes AudienceSegment)
```

External conversations need MiroFish at `http://localhost:5001` and `MIROFISH_BASE_URL=http://localhost:5001`. Conversations are candidate observations; they cannot change deterministic verdicts or inflate the heuristic score. Without a capture, the result explicitly records that limitation. Consumers must check `metrics.score_available`; the numeric zero placeholder does not mean a measured score when that flag is false.

Structured revisions preserve scenario facts, IDs and assertions for local comparison, and archive prior results. Revised prose remains unverified, so the engine prevents a new MiroFish launch from reusing unchanged original wording after a revision. A failed extraction, revision or swarm does not fabricate a successful replacement result.

## Person 3

Built-in `FuzzDesigner` + `RuleEvaluator` run on every create/revise. Population is capped at `MAX_SWARM_AGENTS=50`.

Frontend (Person 1) later uploads:

1. The policy / scenario PDF (`file`)
2. The audience seed (`seed_text` and/or `seed_file`)

Person 2 hands off a revised PolicyIR (`POST /v1/runs/{id}/revise`). Person 3 fuzzes that IR.

Results on `GET /v1/runs/{id}/effectiveness`:

- `score` 0–100 only when `metrics.score_available` is true; otherwise display **Not scored**
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
- `POST /v1/runs/{id}/revise` `{"instruction": "Clarify the receipt threshold"}` — validate a structured revision and rerun the same local scenarios
- `POST /v1/runs/{id}/rehearse?swarm=true` — request MiroFish capture where source wording is still eligible
- `GET /v1/contracts` — generate TypeScript types

CORS defaults to `localhost:5173` and `localhost:3000`.

## Tests / CI

```bash
LLM_MOCK=true pytest -q
```

The repository-root `.github/workflows/ci.yml` runs these tests in the `exploratory-engine` job. Keep the engine and core backend in separate virtual environments because both expose an `app` Python package.

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
