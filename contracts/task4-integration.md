# Task 4 integration contract — version 1.0

Person 1 owns this shared boundary. Import domain types from `app.domain.models`,
protocols from `app.domain.protocols`, and adapters from `app.core`. Feature
modules must not define competing provider requests or stage protocols.

## Stage methods

| Protocol | Method | Result | Execution |
| --- | --- | --- | --- |
| `LLMClient` | `complete_json(LLMRequest)` | `LLMResponse` | async |
| `PolicyCompiler` | `compile(CompilePolicyRequest)` | `PolicyCompilation` | async |
| `RevisionPlanner` | `propose(ProposeRevisionRequest)` | `RevisionProposal` | async |
| `ScenarioPlanner` | `generate_initial(GenerateInitialScenariosRequest)` | `ScenarioBatch` | async |
| `ScenarioPlanner` | `generate_targeted(GenerateTargetedScenariosRequest)` | `ScenarioBatch` | async |
| `ScenarioPlanner` | `assemble_suite(AssembleSuiteRequest)` | `ScenarioSuite` | sync |
| `EvaluationEngine` | `evaluate(EvaluatePolicyRequest)` | `EvaluationReport` | sync |
| `FindingAnalyzer` | `analyze(AnalyzeFindingsRequest)` | `FindingReport` | sync |
| `RevisionApplier` | `apply_revision(ApplyRevisionRequest)` | `PatchApplicationResult` | sync |
| `RegressionAnalyzer` | `compare(CompareRevisionRequest)` | `ComparisonBundle` | sync |

Runtime protocol checks only check structural presence. Typed annotations and
contract tests define the complete signature; runtime checks do not validate a
feature's semantics. `ScenarioBatch.candidates` carries provisional candidates;
the planner still enforces the caller's scenario budget and source restrictions.

## Provider-neutral request

`LLMRequest` has these fields in addition to `schema_version`:

- `operation`: `policy_extraction`, `invariant_suggestion`,
  `scenario_generation`, `targeted_scenario_generation`, or `revision_proposal`.
- `system_instructions`: trusted application instructions.
- `untrusted_payload_json`: serialized JSON object containing policy or scenario
  data. It is never promoted into system instructions.
- `response_schema`: a JSON object schema, normally from `model_json_schema()`.
- `response_schema_name`: 1–64 ASCII letters, digits, underscores or hyphens.
- `generation_config`: the shared integer-based `GenerationConfig`.
- `repair_attempt`: `0` initially and `1` for the single feature repair.

For Person 2's existing prompt builders, map `system_instructions` directly,
map `policy_payload_json` or `payload_json` to `untrusted_payload_json`, and use
`json.loads(response_schema_json)` for the schema. Revision and invariant calls
can supply `RevisionProposal.model_json_schema()` and
`InvariantSuggestions.model_json_schema()` respectively.

```python
import json
from app.domain.models import LLMRequest, PolicyExtraction

request = LLMRequest(
    operation="policy_extraction",
    system_instructions=prompt.system_instructions,
    untrusted_payload_json=prompt.policy_payload_json,
    response_schema=PolicyExtraction.model_json_schema(),
    response_schema_name="PolicyExtraction",
)
response = await llm.complete_json(request)
raw_output = (
    response.output
    if isinstance(response.output, str)
    else json.dumps(response.output, ensure_ascii=False, allow_nan=False)
)
```

`LLMResponse.output` may be a parsed JSON object or a raw string. A stopped
provider response containing malformed JSON must reach `complete_typed` so its
one-repair path can run. Use JSON serialization for an object, never `str(dict)`.
Person 2's strict parsers accept serialized JSON, which correctly maps JSON
arrays into the immutable tuple-based domain models.

Requests, responses, prompts and model output are internal Python interfaces.
They are not `RunView` fields or artifact payloads. Record safe model/configuration
metadata and prompt hashes in the manifest, not full payloads. Repr suppression
is a diagnostic safeguard; it does not make `model_dump()` safe for public logs.

## Compilation and provisional intent

`CompilePolicyRequest(document=document)` starts the future LLM compiler path.
`extraction` is optional; supplying it preserves the current deterministic path.
The existing `compile_baseline_policy` helper requires a populated extraction.
The LLM compiler must construct a populated request before calling that helper;
this contract change does not make the helper perform extraction or call a model.

`InvariantSuggestion` contains `invariant_id`, `description`, `rationale`, typed
`when` predicates, `assertion: AssertionContent`, and
`origin="model_suggestion"`. It has no severity, approval status, oracle origin,
gold label or session-confirmation reference. `InvariantSuggestions.invariant_drafts`
requires three to five suggestions and rejects duplicate identities/semantics.
Derived `daily_category_total_minor` conditions are supported for suggestions;
executable rule predicates remain unchanged.

`PolicyCompilation.invariant_drafts` contains these suggestions. Its empty
backward-compatible default means the deterministic compiler has not generated
suggestions. A completed LLM compiler must validate an `InvariantSuggestions`
result and return three to five entries. It must not treat the empty default as
successful invariant generation.

`InvariantDraft`, `Invariant`, and `PolicyContract` retain their confirmed-intent
meaning. After explicit human review, the coordinator constructs a confirmed
assertion and matching invariant reference. The reviewer supplies severity;
neither a model suggestion nor a default copied from it is an authoritative
severity. `InvariantSummary` is the public review projection and requires that
reviewer-owned severity input. Task 19/20 wiring must account for that step.

## Scripted client and retries

Use `ScriptedLLMClient` with queued typed `LLMResponse` or `LLMTransportError`
outcomes. It records an independent request snapshot on every call, consumes one
outcome per call and fails safely when exhausted. It never repeats an outcome
or silently supplies an empty result. Queue copies preserve fixture independence.

```python
from app.core.errors import LLMTransportError
from app.core.fakes import ScriptedLLMClient
from app.core.llm import RetryingLLMClient
from app.domain.models import LLMError, LLMResponse

scripted = ScriptedLLMClient([
    LLMTransportError(LLMError(code="timeout", operation="policy_extraction")),
    LLMResponse(output={"rules": []}),
])
llm = RetryingLLMClient(scripted, sleep=no_sleep)  # async test helper
response = await llm.complete_json(request)
assert response.usage.transport_retries == 1
```

The short response above demonstrates transport behavior, not a schema-valid
policy extraction. Feature tests must queue complete typed extraction fixtures.

Wrap a single-attempt delegate in `RetryingLLMClient`. Only typed `timeout` and
`rate_limit` errors retry: the initial call plus at most two retries, with awaited
1-second and 2-second backoffs. The third failure ends the request. Cancellation,
refusal, invalid output, authentication, invalid requests, connection/server
failures and arbitrary programming exceptions do not trigger this retry policy.
Directly nested retry wrappers are rejected. SDK retries are disabled.

Person 2's `complete_typed` owns schema validation and the one repair request;
Task 4 does not implement that feature. Repair uses `repair_attempt=1` with the
same operation and bounded, sanitized validation paths/codes. Never send raw
exception text, arbitrary user-supplied field names or raw model output as trusted
instructions. A repair is a separate logical request with its own transport
budget; at most six provider attempts are possible across the initial request
and one repair. Usage counters describe a logical request, not unlimited run
totals. The coordinator aggregates actual run activity separately.

## OpenAI mapping and configuration

The OpenAI adapter uses the official SDK's asynchronous Chat Completions API.
It sends trusted instructions as a system message and the delimited JSON payload
as a separate user message, with no external tools. It supplies the original
response schema with `strict=False`; it does not silently rewrite Pydantic
constraints or claim provider enforcement of validators. Feature-level Pydantic
validation and deterministic checks remain mandatory.

The configured model must support the requested endpoint, schema format and
generation parameters. Unsupported combinations fail safely; the adapter does
not silently drop parameters or change models. `max_output_tokens` maps to
`max_completion_tokens`; temperature and top-p convert from their integer units;
seed is supplied only when present. Seed does not guarantee model determinism.

`Settings` reads server environment variables. Cached mode is the default and
needs no provider credentials. Live adapter construction requires `LLM_MODEL`
and `OPENAI_API_KEY`. Credentials use `SecretStr`. The defaults are a 3,600-second
run TTL, 50,000 policy characters and a 30-second model timeout. No environment
file is loaded automatically and no credentials are written by this task.

Live construction uses `OpenAILLMClient.from_settings(settings)`; wrap that
single-attempt adapter in `RetryingLLMClient`. Close the owned adapter with
`await adapter.aclose()` at application shutdown. Tests inject a fake SDK client;
SDK retry settings are disabled even for an injected client.

Errors cross the boundary as safe typed codes. SDK messages, response bodies,
refusal text, keys and policy contents are not public error messages. Ordinary
malformed text is returned for feature repair; refusals, truncated completions,
missing content and invalid provider responses are safe typed failures.
`to_public_error` projects fixed messages for the future API. Its public
`retryable` flag can indicate that a user may try again; it does not alter the
transport wrapper's timeout/rate-limit-only automatic retry rule.

## Person 2 next steps

1. Implement `complete_typed` with strict JSON parsing, one sanitized repair and
   safe terminal `ModelOutputValidationError(repair_attempted=True)` behavior.
2. Wire `extract_policy` and `LLMPolicyCompiler` through `LLMClient` and populated
   deterministic compilation requests.
3. Map the provisional fixture suggestions to `InvariantSuggestions`, assign
   stable IDs and return `PolicyCompilation.invariant_drafts`.
4. Implement `LLMRevisionPlanner.propose` against the shared proposal contract
   and existing deterministic validation.
5. Ensure model-produced unsupported clauses cannot retain a claimed
   `session_confirmed` review status. Prompt instructions alone do not enforce it.
6. Sanitize feature error chains and repair diagnostics before public projection.

Task 4 freezes the shared interfaces and fake-tested adapter mapping. It does
not complete those Person 2 wrappers, actual provider acceptance, Task 19/20
coordination/API wiring, or the final benchmark and recording gates.
