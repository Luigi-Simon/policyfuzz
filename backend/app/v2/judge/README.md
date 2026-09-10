# PolicyFuzz Judge Agent

The Judge turns the supplied Metric evidence and public Sandbox conversations into English advice: a summary, cited pros and cons, actionable next steps, and evidenced stakeholder interactions. It implements the shared `JudgeService` protocol and returns the canonical `JudgeResult`.

The implementation lives on `p3/feat-v2-judge`, based on the shared Judge checkpoint `2a887b5`. Integration target: `p1/feat-policyfuzz-v2`. Simon wires this service into the Orchestrator and evidence screen; this work does not add an API, database, or frontend. Sandbox development remains in its separate worktree.

## Integration

```python
from app.core.config import Settings
from app.v2.judge.client import OpenAIJudgeClient
from app.v2.judge.service import JudgeAgentService
from app.v2.judge_contracts import validate_judge_result

# Create once at application startup using Core's existing configuration.
client = OpenAIJudgeClient.from_settings(Settings())
judge = JudgeAgentService(client, timeout_seconds=90, max_repairs=1)

# Inside the Orchestrator's async workflow:
result = await judge.run(validated_judge_request)
validate_judge_result(validated_judge_request, result)

# At application shutdown:
await client.aclose()
```

Existing settings: `LLM_MODEL`, `OPENAI_API_KEY`, optional `LLM_BASE_URL`, and `LLM_TIMEOUT_SECONDS` (per provider request, default 30 seconds). There is no default model or embedded credential. Core's settings read environment variables; loading a dotenv file requires explicit `Settings(_env_file=".env")`. Never commit that file.

The default client uses OpenAI strict JSON-schema output. For a configured compatible endpoint that supports JSON-object output only, explicitly pass `response_format="json_object"` to `from_settings`. Both modes use identical local validation and semantic review. There is no automatic provider, response-format, or fixture fallback. The endpoint must support the selected response format and Chat Completions parameters.

No dependency or shared-schema changes are requested: the existing `openai` and `pydantic` dependencies are sufficient. Core may choose a separate Judge model later through the injected client without changing public contracts.

## Independent local check

From the repository root, with Python 3.12 or newer:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -e './backend[dev]'
backend/.venv/bin/python -m pytest backend/tests/v2/test_judge_contracts.py backend/tests/v2/judge -q
PYTHONPATH=backend backend/.venv/bin/python -m app.v2.export_judge --check
```

These tests use fake clients only. They require no API key, running Metric service, or MiroFish instance.

To call a configured live Judge against the supplied **mock** evidence, export the settings above and run:

```bash
PYTHONPATH=backend backend/.venv/bin/python - <<'PY'
import asyncio
from pathlib import Path
from app.core.config import Settings
from app.v2.judge.client import OpenAIJudgeClient
from app.v2.judge.service import JudgeAgentService
from app.v2.judge_contracts import JudgeRequest, validate_judge_result

request = JudgeRequest.model_validate_json(
    Path("contracts/v2-judge/fixtures/complete-request.json").read_text()
)

async def main():
    client = OpenAIJudgeClient.from_settings(Settings())
    try:
        result = await JudgeAgentService(client).run(request)
        validate_judge_result(request, result)
        print(result.model_dump_json(indent=2))
    finally:
        await client.aclose()

asyncio.run(main())
PY
```

Only synthetic or explicitly non-confidential evidence belongs in this workflow. The command makes paid model requests using the configured account.

## Evidence and output guarantees

- The service snapshots and revalidates the request, preserves run/request/policy identity, and computes the canonical request fingerprint. Model output cannot write identity, execution mode, status, or Metric verdict/count fields.
- Every citation resolves against the supplied evidence. Step IDs resolve inside their owning case. Duplicate references and unavailable-translation citations are rejected.
- A key interaction cites both ends of a supplied, ordered reply between different participants. A lone statement can appear as a cited observation in pros/cons. Ordering alone never proves a reply.
- Missing, unscored, incomplete, untranslated, or underrepresented input produces `partial` advice with explicit limitations. Pilot recommendations are blocked for these inputs, failing cases, and fixture evidence. `completed` describes the Judge's evidence processing, not a safe policy.
- Authored fixtures remain mock evidence even when the Judge itself runs live. Relevant findings and the summary carry explicit mock labels, so provenance survives separate display in the UI.
- Trusted instructions and untrusted evidence travel separately. A second model request checks semantic support, unchanged Metric facts, actual interactions, material limitations, provenance, and English prose. It is a validation tool within the Judge role, keeping the four product roles unchanged.
- English is requested in both calls and checked using typed output, a conservative script check, and semantic review. Proper names should be supplied in English display form. No raw provider exception or unvalidated draft appears in a public result.

## Failure and resource behavior

The default allows one repair: at most two advice attempts and two grounding reviews, within a single 90-second deadline. Invalid drafts skip the review. Provider SDK retries are disabled. Repairs receive controlled issue codes and, after a semantic rejection, the prior draft and brief feedback identifying the finding and evidence mismatch. That feedback remains untrusted private input and is checked against the original evidence. No raw exception messages are supplied. Transport failure ends the run immediately; cancellation propagates to Core.

The repair budget is shared across format and semantic failures. If the first draft is malformed, its repair can still fail semantic review and exhaust the default budget. Core can explicitly select `max_repairs=2` and a suitable overall deadline to allow another correction; this does not weaken any acceptance check.

Malformed or unsupported advice returns `failed`, `insufficient_evidence`, a sanitized error, and no findings or next steps. Invalid request identity or ambiguous evidence raises `ValueError` before a provider call; Core should handle this as an invalid integration input. Missing provider configuration raises a startup configuration error.

Defaults limit the evidence payload to 512 KiB and each provider response to 128 KiB. Oversized evidence fails explicitly without truncation. The provider output budget is 8,192 tokens per call. Constructor bounds allow 0–2 repairs, deadlines up to 600 seconds, and evidence limits up to 2 MiB. Provider context/schema limits may impose a smaller practical ceiling.

## Limits and Core handoff

Semantic review uses the same configured model in a separate request. It can incorrectly approve or reject a claim; it is not a proof of policy correctness or a complete language detector. Exact identity, references, gates, and unchanged input facts are enforced in Python; the quality of prose still needs review.

`JudgeRequest` does not contain full original policy text. Advice is limited to supplied interpretations, traces and public dialogue. The shared mock Sandbox dialogue does not analyze the reimbursement policy; it cannot establish policy-specific sentiment. A real combined run must come from the Orchestrator with matching evidence identity, not relabelled older runs.

Owned implementation files are `__init__.py`, `client.py`, `evidence.py`, `prompts.py`, `schema.py`, and `service.py`; adapter tests are under `backend/tests/v2/judge/`. `schema.py` derives provider schemas from the canonical result model; its private review-tool output is not a new public Judge contract. The accompanying live evidence note records verification and outstanding integration work.
