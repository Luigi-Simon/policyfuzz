# MiroFish Sandbox Agent

Implements `app.v2.protocols.SandboxService` as
`app.v2.sandbox.service.MiroFishSandboxService`. All changes stay in the two
Sandbox-owned folders. The Orchestrator, Metric Agent, Judge, API and UI remain
Simon's integration work.

The personality seed produces an exact roster of individual stakeholders. That
roster becomes native MiroFish/OASIS profiles; graph-entity sampling does not
choose the population. Persona generation receives the policy, personality seed,
optional random seed and explicit context. It does not receive Metric scenarios,
test budgets, expected verdicts or previous findings. Scenario circumstances are
passed separately to the simulation profiles.

## Connect from the orchestrator

```python
from app.v2.contracts import public_sandbox_result, validate_sandbox_result
from app.v2.sandbox.language import OpenAILanguageTools
from app.v2.sandbox.service import MiroFishSandboxService
from app.v2.sandbox.transport import MiroFishClient

transport = MiroFishClient(base_url="http://127.0.0.1:5002")
language = OpenAILanguageTools(
    model=configured_model,
    api_key=configured_key,
    base_url=configured_provider_url,
)
sandbox = MiroFishSandboxService(transport, language)

try:
    result = await sandbox.run(request)
    validate_sandbox_result(request, result)
    judge_evidence = public_sandbox_result(result)
    # Give this projection to the Judge. Validate its cited message IDs against
    # judge_evidence["messages"]. Do not serialize result.original_records.
finally:
    await transport.close()
    await language.close()
```

Both clients and language tools are injectable. Automated tests use fakes only.
The transport and language tool close only HTTP/SDK clients they created.
The owning application should keep service instances alive for repeated requests,
then close their clients on application shutdown.

## Run MiroFish

Keep the existing MiroFish environment separate from the PolicyFuzz backend.
From this repository root:

```bash
/path/to/MiroFish/backend/.venv/bin/python backend/app/v2/sandbox/serve_mirofish.py \
  --root /path/to/MiroFish --port 5002
```

This installs the owned `/api/policyfuzz/v2` extension into the running Flask app.
It does not modify the MiroFish checkout's source. The extension uses MiroFish's
profile exporter, simulation manager, native Twitter runner and OASIS agents.
The launcher imports the canonical PolicyFuzz request model under a separate
module name because both projects use a Python package named `app`.

The server binds to localhost. It is a local development integration; shared
deployment authentication and access control belong to the hosting application.
Its job journal defaults to `MiroFish/backend/uploads/policyfuzz-v2-jobs.sqlite`;
`--journal` can select a different durable path. Keep this journal together with
MiroFish's project/simulation files. They contain source text, profiles and raw
evidence. Do not delete the journal while associated jobs may still be running.

The internal extension supports lookup, prepare, start and stop by complete request
fingerprint. Its endpoints are specific to this adapter, not undocumented upstream
MiroFish options. Native `/api/simulation/<id>/posts`, `/comments` and `/actions`
are used for paginated capture.

## Counts, interaction and timing

- The adapter supports 1–50 participants. The shared contract allows 1–100; a
  request above the adapter cap reports requested/configured/observed counts and
  a partial result. A smaller `max_agents` may be configured explicitly.
- Every configured participant is scheduled in every requested round, up to the
  contract's 20-round cap. This controls actual native execution, not just prompt
  wording. The optional random seed controls Python randomization in the runner;
  it does not promise deterministic model output.
- In populations above one, the owned peer feed shows up to 20 real posts by
  other participants. Native comment expansion includes their recorded replies.
  Self-replies and self-quotes are rejected; they are never silently retargeted.
  The native model still chooses the target and authors the content. This is a
  controlled discussion configuration, not MiroFish's default relevance feed.
- Opening posts come from persona generation. They are clearly identified in
  source titles and are not proof of interaction. A result is partial unless
  every configured participant has a captured reply to another participant.
  A one-person request cannot demonstrate cross-participant interaction.
- `observed_stakeholder_count` follows the shared definition: distinct captured
  authors, including openings. `interaction_coverage:` gives the separate verified
  reply-author count. Do not present observed count as proof of a conversation graph.
- MiroFish/OASIS's `created_at` is a simulation step in the tested version.
  Only jobs explicitly marked `clock=oasis_step_v1` map step 1..N to rounds; step
  zero is the seeded opening. Wall-clock `recorded_at` remains null. Other
  timestamps are parsed only when supplied in a supported ISO format.
- Sequence is stable presentation order constrained by validated reply links.
  It does not invent sub-round chronology. Unresolved links, cycles, conflicting
  IDs, unsupported timestamps and unknown speakers are surfaced as limitations.

## Evidence and English output

Stable message/source/persona IDs include the simulation ID and full request
fingerprint. Changing any request setting, including policy version or exact
text, produces a separate version-bound job. Equal text from different speakers
is retained; duplicate delivery of the same source ID is deduplicated. Quotes use
the quoting author's own `quote_content`, never the original author's text.

Text is parsed before translation. Language tools receive human-readable text
only. IDs, timing, counts and reply relationships never enter their output schema.
English originals remain byte-for-byte unchanged. Non-English and mixed-language
messages are translated, checked for unchanged numeric values, and reviewed in a
separate provider call for eligibility, negation, limits, modality and uncertainty.
This review is a useful check, not a guarantee of translation accuracy. Failed or
unchanged translations use the exact shared English unavailable placeholder.

`public_sandbox_result` contains English messages and evidence excerpts. Original
records are retained in `result.original_records` and excluded from that projection.
`service.internal_capture(fingerprint)` returns an immutable JSON diagnostic snapshot
with raw rows, including malformed/unknown records and original metadata. It keeps
the last 16 captures in memory; durable raw files remain in MiroFish. Do not expose
either internal representation to the browser or Judge.

Conversation claims remain simulated observations. Participants may invent or
misinterpret provisions despite the prompts; the Judge must compare claims with
the supplied policy. This component assigns no authoritative policy verdict,
population sentiment percentage, or final recommendation.

## Lifecycle and failures

The SQLite journal persists a claim before creating a project or starting a runner.
Repeated and concurrent prepare/start requests cannot silently launch duplicates.
Safe retries reuse the stored roster and simulation for the exact request.
An uncertain preparation without a known simulation ID remains explicitly
`prepare_uncertain`; it requires inspection rather than another automatic launch.
Cancellation during an in-flight prepare is recorded by fingerprint, so a late
request cannot start after cancellation. Changing the request means a new job.

80% of `request.timeout_seconds` is reserved for persona generation and execution;
the remainder is available for capture and English projection. Polling, provider
calls and cleanup are bounded. Stop acknowledgement has a separate default
10-second bound and may extend the total elapsed time by that much. A timeout or
provider failure never becomes fixture data. Successful independent capture
endpoints are retained when another endpoint fails. The default capture cap is
500 rows per endpoint; reaching it is explicitly incomplete.

`run()` converts task cancellation to a typed cancelled result and requests native
stop. It may return partial if translations are unavailable, as required by the
current shared validator. Check the result's status and prefixed errors/limitations,
not just whether the coroutine raised an exception. Failed stop acknowledgement
is explicit; do not assume the upstream process is stopped.

## Items for Simon

No shared contracts or dependency files were changed.

1. Declare `httpx` as a direct production dependency when integrating. It is
   currently present through OpenAI's dependencies and the existing dev extra.
   Flask and OASIS are needed only in the existing MiroFish environment.
2. The shared validator requires `result.policy_title == request.policy_title`
   while forbidding Han text in that result field. A non-English policy title
   cannot be faithfully translated without a shared contract revision. Such titles
   are rejected before execution. Add a separate English display title or bind the
   original title internally in a coordinated schema change.
3. The validator requires unavailable translations to have `partial` status even
   after cancellation/failure. This adapter retains `cancelled:` /
   `simulation_cancelled:` / `simulation_failed:` diagnostics while following that
   rule. Consider independent execution and projection statuses in the shared model.
4. `errors` and `limitations` are string tuples in the foundation. They use stable
   code prefixes here; typed diagnostic objects require a shared contract change.
5. The unchanged legacy packaging script can fail its outside-repository entry
   test with `ModuleNotFoundError: scripts.verify_submission`. Its import-path
   fix is outside the Sandbox-owned paths.

## Checks and live sample

Use the PolicyFuzz backend's development environment. The commands below assume
an environment at `backend/.venv`. This separate worktree reused
`/Users/a123/Desktop/policyfuzz/policyfuzzCode/backend/.venv/bin/python`; substitute
that interpreter locally, or install the backend development environment in a
fresh checkout before running these commands from the repository root:

```bash
backend/.venv/bin/python scripts/check_v2_foundation.py
cd backend
.venv/bin/python -m pytest tests/v2/sandbox -q
.venv/bin/python -m ruff check app/v2/sandbox tests/v2/sandbox
```

For an explicitly selected small real-provider check, provide `LLM_API_KEY` (or
`OPENAI_API_KEY`), `LLM_MODEL_NAME` (or `LLM_MODEL`) and optional `LLM_BASE_URL` in
the environment used by the PolicyFuzz process. These should match the configured
MiroFish provider. Never pass a key as a command argument or commit `.env`.

```bash
cd backend
.venv/bin/python -m app.v2.sandbox.smoke --live \
  --count 3 --rounds 2 --request-id my-synthetic-sandbox-check \
  --output /tmp/policyfuzz-sandbox-check
```

The smoke command uses the shared synthetic transit policy. Reusing the exact
request ID and settings resumes the same job; use a new ID for a fresh run. It
writes a public result separately from backend-only originals and raw capture.
The committed live record and remaining integration milestone are documented in
[LIVE_EVIDENCE.md](LIVE_EVIDENCE.md).

Implementation references: [MiroFish source](https://github.com/666ghj/MiroFish)
and [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
