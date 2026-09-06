# Person 3 — fuzz planning and sidecar handoff

Status: Tasks 8–11 implemented against frozen version 1.0 contracts. The
pre-existing sidecar HTTP client remains available and unchanged except for its
`Self` return annotation/formatting.

## Planner integration

```python
from app.features.fuzzing import DefaultScenarioPlanner

planner = DefaultScenarioPlanner(llm, manifest=run_manifest)
```

The implementation has the exact public `ScenarioPlanner` methods:

```python
async def generate_initial(
    request: GenerateInitialScenariosRequest,
) -> ScenarioBatch: ...

async def generate_targeted(
    request: GenerateTargetedScenariosRequest,
) -> ScenarioBatch: ...

def assemble_suite(request: AssembleSuiteRequest) -> ScenarioSuite: ...
```

`DefaultScenarioPlanner()` is supported for deterministic mechanical-only use.
Supplying an LLM requires the matching per-run manifest. The container must keep
one planner instance for the run so the one-adaptation limit and rejection
statistics remain bound to that run.

The planner enforces 10 initial accepted scenarios, five targeted accepted
scenarios, 15 total scenarios, and one targeted call. It attaches every
facts-matched confirmed invariant assertion from the trusted contract before
returning a batch. This keeps evaluator-produced assertion rows equal to the
frozen scenario assertion IDs without allowing the model to author answers.

## Scripted exploratory output

The stable private response models and an offline fixture helper are public
feature exports:

```python
from app.features.fuzzing import (
    ExploratoryBatchPayload,
    ExploratoryScenarioPayload,
    exploratory_prompt_commitment,
    exploratory_response_example,
)
from app.domain.models import LLMResponse

response = LLMResponse(
    output=exploratory_response_example(
        rule_id="rule-example",
        invariant_id="invariant-example",
    )
)
```

An empty successful scripted response is `{"scenarios": []}`. The schema name
is `policyfuzz_exploratory_batch_v1`. Output contains only category, all eight
fact fields, target IDs, and a 1–240 character rationale. Extra assertion,
outcome, finding, severity, or revision keys fail schema validation. Invalid
output receives one repair using the same frozen scenario operation and
`repair_attempt=1`; a second failure raises sanitized
`ModelOutputValidationError` without source or output values.

`exploratory_prompt_commitment()` returns the exact
`fuzz_prompt_source_v1` manifest entry for the trusted instructions and private
response schema. A planner with an LLM rejects a manifest missing this exact
commitment before making a call. Model-authored exact policy/invariant numeric
thresholds, including derived daily totals, are rejected into the one bounded
repair; Python retains sole ownership of boundary cases.

## Deterministic behavior

- Mechanical synthesis starts from eight complete stored facts, solves typed
  AND-only predicates, and emits every in-domain exact `n-1`, `n`, `n+1`
  numeric neighbor. Derived daily totals split across both stored amount fields.
- Each rule gets a normal satisfying witness when satisfiable. Each invariant
  gets a protected assertion-bearing satisfying witness. Boundary neighbors
  carry an invariant assertion only while the full invariant condition matches.
- Canonicalization revalidates candidates, rejects unknown targets and invalid
  assertions, excludes already-used facts, merges compatible facts/partition
  duplicates, and greedily selects protected cases, category diversity, target
  gain, mechanical origin, then semantic hash.
- Scenario IDs hash complete facts, sorted assertions/targets, protection, and
  partition. Origins, input candidate IDs, category, timestamps, and order do
  not affect identity.
- The frozen version 1.0 rejection vocabulary is retained in suite statistics:
  `invalid_facts`, `invalid_assertion`, `duplicate`, `budget_exceeded`, and
  `incompatible_assertions`.
- Coverage counts only evaluator evidence. Required coverage is all rules and
  confirmed invariants; predicate branch totals/counts follow the evaluator's
  rule-predicate coordinates.
- Suite `content_sha256` uses `canonical_sha256` over
  `complete_payload_projection(ScenarioSuite)`, which removes only the suite's
  self-hash and retains its document, contract, semantic rule-set, engine, seed,
  scenarios, and statistics anchors.

The coordinator owns the final insufficient-coverage stop because frozen
`AssembleSuiteRequest` contains no coverage. `ScenarioBatch` contains no
rejections, so feature-local canonicalization detail is retained by the per-run
planner and emitted through `ScenarioSuite.statistics` at assembly.

## Development evidence

The final synthetic development policy and confirmed contract produce:

| Evidence | Result |
| --- | --- |
| Initial accepted scenarios | 10 |
| Targeted scenarios required | 0 |
| Rule coverage | 10 / 10 |
| Confirmed invariant coverage | 3 / 3 |
| Baseline findings | conflict, daily-cap intent breach, receipt structural gap |
| Remaining findings after scripted revision | 0 |
| Patch acceptance | all seven gates passed |
| Live/provider calls | 0 |

`backend/.venv/bin/python scripts/offline_smoke.py` returned status `passed`,
scenario count 10, baseline defects 3, remaining defects 0, and patch accepted.

## Files

- `backend/app/features/fuzzing/{constants,synthesis,prompts,exploratory,canonicalize,coverage,planner}.py`
- `backend/app/features/fuzzing/__init__.py`
- `backend/app/features/fuzzing/engine_client.py`
- `backend/tests/features/fuzzing/test_{synthesis,exploratory,canonicalize,coverage,planner}.py`
- Existing `engine_client.py`, `types.py`, and `test_engine_client.py` sidecar
  behavior remains supported.

## Verification

- Focused fuzzing tests: 41 passed.
- Fuzzing coverage: 91% across the complete package, including the legacy
  sidecar; new deterministic modules are 90–97% individually.
- Owned Ruff check and format check: passed.
- Concrete API and real-stage demo regression reproductions: four passed.
- Full backend run: 1,287 passed; two unrelated submission archive atomicity
  tests failed in `tests/integration/test_submission_package.py`.
- Full backend Ruff found four unrelated import-order findings in integration
  tests outside Person 3 ownership.

No Git mutation or commit was made, as required by the remaining-work packet.
