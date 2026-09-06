# Policy rehearsal engine — API reference

Share this folder with the frontend developer. They do **not** need your `localhost` URL.

| File | Use |
|------|-----|
| `API.md` | This page — human-readable endpoints |
| `openapi.json` | Paste into [Swagger Editor](https://editor.swagger.io) or generate a client |
| `contracts.json` | JSON Schema for TypeScript types (`PolicyIR`, `ScenarioSuite`, …) |
| `swagger.html` | Open in a browser (needs internet once for the Swagger UI script) |

Live server (your laptop only): `GET /download/api-docs.zip` downloads this pack as a zip.

Base URL when the engine is running locally: `http://127.0.0.1:8000`

---

## Flow the UI should follow

1. `POST /v1/runs` — upload policy PDF + audience seed (`seed_text` and/or `seed_file`)
2. `GET /v1/runs/{run_id}` — IR, ≤50 fuzz agents, preview score
3. `GET /v1/runs/{run_id}/effectiveness` — 0–100 score, justification, recommended actions
4. `POST /v1/runs/{run_id}/rehearse?swarm=true` — run MiroFish (needs `MIROFISH_BASE_URL`) and rescore
5. (optional) `POST /v1/runs/{run_id}/revise` — Person 2 rewrite, then Person 3 regenerates agents  

---

## Endpoints

### `GET /health`

Liveness. No auth.

```json
{ "status": "ok", "service": "policy-engine", "version": "0.1.0", "llm": false, "mirofish": false }
```

### `GET /v1/contracts`

JSON Schema for every shared model. Generate TS with e.g. `json-schema-to-typescript`.

Keys: `PolicyDocument`, `PolicyIR`, `SeedSpec`, `AudienceSegment`, `ScenarioSuite`, `RunRecord`, `EvaluationReport`, `PolicyEffectivenessReport`, `MiroFishPack`.

### `POST /v1/runs`

Create a run. **multipart/form-data**.

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `file` | PDF, TXT, or MD | one of file/policy_text | Policy document |
| `policy_text` | string | one of file/policy_text | Paste policy instead of uploading |
| `seed_text` | string | no | Freeform population / personality notes |
| `seed_file` | PDF, TXT, or MD | no | Audience seed; text is merged into `seed_text` |
| `population_size` | int | no | Capped at 50 |
| `groups` | string | no | Comma-separated shorthand groups |
| `audience_json` | string | no | Structured segments JSON (see below) |
| `locale` | string | no | Optional locale / jurisdiction label |

**`audience_json`** (preferred for injectable profiles):

```json
[
  {"id": "parents", "label": "Parents", "weight": 2, "attributes": {"age_band": "30-45"}},
  {"id": "students", "label": "Students", "weight": 3, "attributes": {"age": 16}}
]
```

Or `{ "segments": [ ... ] }`. Segment attributes are copied onto fuzz agents as `actor.*` facts.

Returns `RunRecord`. `status` is `completed` after Person 3 fuzz + grade. `effectiveness.score` is 0–100 from the fuzzer (swarm not required). `population_size` above 50 is clipped.

```bash
curl -X POST http://127.0.0.1:8000/v1/runs \
  -F "policy_text=Students must not use phones in class." \
  -F "seed_text=Urban high school community" \
  -F "population_size=20" \
  -F "locale=any" \
  -F 'audience_json=[{"id":"students","label":"Students","weight":3},{"id":"teachers","label":"Teachers","weight":1}]'
```

### `GET /v1/runs`

List recent runs. Query: `limit` (default 50).

Returns `RunSummary[]`: `run_id`, `status`, `message`, `policy_id`, `policy_revision`, `rule_count`, `scenario_count`, `score`, `error`.

### `GET /v1/runs/{run_id}`

Full `RunRecord`: document, IR, suite, evaluation, effectiveness, MiroFish pack, seed.

`404` if unknown.

### `GET /v1/runs/{run_id}/ir`

`PolicyIR` only — person 3’s input.

### `POST /v1/runs/{run_id}/revise`

JSON body:

```json
{ "instruction": "Exempt grade 12 students" }
```

Recompiles IR, regenerates ≤50 fuzz agents, rebuilds the pack, and rescores.

### `POST /v1/runs/{run_id}/scenarios`

Person 3 output. JSON `ScenarioSuite`.

`policy_id` must match the run’s IR. Each scenario:

- `kind`: `normal` \| `boundary` \| `adversarial` \| `targeted`
- `facts`: dotted paths (`actor.role`, `action.name`, `context.*`)
- `targeted_rule_ids`: rule ids from the IR
- `expected_outcome` (optional): `compliant` \| `violation` \| `exception` \| `ambiguous`

Rebuilds the MiroFish pack from the named agents.

### `GET /v1/runs/{run_id}/scenarios`

The attached `ScenarioSuite`. `404` if none yet.

### `GET /v1/runs/{run_id}/mirofish`

`MiroFishPack`: `seed_markdown`, `simulation_requirement`, `population_size`, `agent_count`, `launch`.

### `GET /v1/runs/{run_id}/mirofish/seed.md`

Downloads the seed as markdown (upload this in the MiroFish UI).

### `POST /v1/runs/{run_id}/mirofish?launch=true`

Rebuild pack. `launch=true` POSTs ontology into MiroFish if `MIROFISH_BASE_URL` is set.

### `GET /v1/runs/{run_id}/evaluation`

`EvaluationReport`: per-scenario pass/fail with witness traces. This is the handoff back to Person 2's repair agent.

### `GET /v1/runs/{run_id}/effectiveness`

`PolicyEffectivenessReport`:

- `score` 0–100
- `justification` (fuzz + named swarm posts when available)
- `highlights` significant agent interactions
- `recommended_actions` for improving the policy

### `POST /v1/runs/{run_id}/rehearse?swarm=true`

Person 3 rehearsal. Regenerates missing agents, grades, and if `swarm=true` and MiroFish is configured, runs ontology → graph → simulate (≤50 agents, `MIROFISH_MAX_ROUNDS` default 8) then rescores.

---

## Status values

`pending` → `ingesting` → `extracting` → `compiling` → `generating_scenarios` → `evaluating` → `rehearsing` → `completed`  
or `failed`.

Frontend: `POST /v1/runs` waits until the fuzz score is ready. Swarm is a separate `rehearse` call.

## CORS

Default origins: `http://localhost:5173`, `http://localhost:3000`. Override with `CORS_ORIGINS` in `.env`.

## Errors

JSON `{ "detail": "..." }` with `400` or `404`.
