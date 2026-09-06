# Task 19 workflow integration

Task 19 supplies the in-memory coordinator behind the frozen version 1.0
contracts. Task 20 connects it to HTTP. Specialist implementations are injected;
the workflow does not implement policy interpretation, scenario synthesis,
evaluation, patch application, or regression verdicts.

## Public boundary

Use `app.workflow.coordinator.RunCoordinator`. Its methods consume the existing
`CreateRunRequest`, `ConfirmContractRequest`, `SelectFindingsRequest`, and
`ConfirmRevisionRequest` from `app.domain.models`. Creation returns
`CreateRunResponse`; reads and decisions return the existing `RunView`.
`start(run_id)` performs the initial work after creation. The HTTP layer must
schedule and await work through its task runner rather than invent another state
machine.

The published OpenAPI, `RunView`, and JSON schemas remain the integration
contract. Older plan examples containing `version`, `mode_label`, or nested
`baseline` fields in `RunView` are superseded by those published models. The UI
already derives the mode label from `mode`.

## Dependencies

The coordinator takes explicit keyword dependencies:

| Dependency | Responsibility |
| --- | --- |
| `store`, `clock` | Versioned storage and wall/monotonic time |
| `policy_compiler` | `PolicyCompiler.compile` |
| `scenario_planner` | Initial/targeted generation and suite assembly |
| `evaluation_engine` | Deterministic evaluation and measured coverage |
| `finding_analyzer` | Deterministic grouped findings |
| `revision_planner` | One proposed structured revision |
| `revision_applier` | Validated atomic structured patch |
| `regression_analyzer` | Frozen-suite comparison and seven acceptance gates |
| `ingest` | Callable from `CreateRunRequest` to `PolicyDocument` |
| `metrics` | Deterministic callable from `MetricsRequest` to `MetricsReport` |
| `manifest_factory` | Callable from run ID and mode to `RunManifest` |
| `draft_severity` | Host-selected, unconfirmed review-form default |

Optional `mode`, `run_id_factory`, and `cached_loader` select execution and
replay behavior. Production wiring belongs in Task 20. Tests use the scripted
classes in `app.workflow.fake_stages`; exhausted scripts fail explicitly.

## Storage and decisions

`RunStore` owns a lock and monotonic deadline for each run. Its private
`StoredRun` includes a version for compare-and-swap mutations, source request,
and pending confirmation. It is not a public schema or an artifact payload.
Do not hash that subclass as though it were the concrete domain `RunRecord`.

Retention is at most 3,600 seconds. Wall-clock adjustments do not extend it.
Deletion and shutdown discard stored data; an in-flight stage cannot recreate a
deleted or expired run. State transitions claim work before calling an awaited
stage, preventing duplicate decisions from launching duplicate work.

`RunCoordinator.delete_run` also cancels its active asynchronous stage tasks.
Direct store expiry or `RunStore.aclose` invalidates writes but does not cancel
an injected stage. Task 20's task runner must cancel and drain jobs on expiry and
shutdown; storage cleanup alone is not a complete server lifecycle.

Contract confirmation uses the exact provisional baseline policy ID and its
complete artifact hash. Revision confirmation uses the displayed proposal ID.
Finding selection uses the complete displayed set of reviewable IDs. The frozen
HTTP models do not contain the extra expected-semantic-hash fields in the old
plan. Review artifacts cannot be edited in place while awaiting decisions;
one-shot state transitions and private versions enforce this narrower contract.

The compiler must return three to five provisional invariant suggestions for an
interactive run. An empty suggestion list is valid for the deterministic
compiler helper but insufficient for this flow and produces a safe failure.
The host's draft severity is only a form default. A confirmed `PolicyContract`
uses the severity explicitly submitted in the user's confirmation. Model output
does not assign severity or confirmation provenance.

Accepted structural gaps/conflicts require reviewer severity. Findings tied to
a confirmed invariant retain its severity. Candidate findings and private
witnesses cannot be accepted as targets. Rejecting the contract, every finding,
or the revision ends the run without downstream work.

## Execution and hashes

The coordinator requests at most ten initial candidates, measures coverage from
the provisional evaluation, and permits at most one targeted batch of five.
The total accepted suite is capped at fifteen. Required coverage means every
rule and confirmed invariant is exercised; additional predicate-branch coverage
is measured. Insufficient required coverage ends the run before revision.

After coverage succeeds, the final suite is frozen and evaluated again for the
authoritative baseline. Revision retesting uses the identical frozen suite,
contract, engine, and manifest. Only the evaluated policy changes. A later-stage
failure retains earlier completed artifacts for inspection.

| Anchor | Digest |
| --- | --- |
| Document and quote | Exact UTF-8 source digest |
| Confirmation baseline policy | Complete provisional policy payload |
| Suite/proposal `rule_set_sha256` | Semantic confirmed baseline policy |
| Evaluation `policy_sha256` | Complete evaluated policy payload |
| Contract, suite, manifest inputs | Complete corresponding payloads |
| Suite `content_sha256` | Complete suite projection excluding its self-hash |
| Engine | Manifest's engine commitment |

Use `app.core.artifacts` projections and `canonical_sha256`; plain dictionaries
do not receive type-specific hash exclusions. Stage outputs are checked against
their supplied input anchors before becoming workflow evidence.

## Public evidence and model isolation

`to_run_view` explicitly constructs the permitted public fields. Events,
artifact titles, and finding summaries use safe fixed text. Document contents,
prompts, provider errors, scenario facts, assertion answers, and benchmark labels
are not copied into the view. Intent assertions in the confirmation form and
exact policy citation excerpts are intentional review content.

Only known visible scenario traces and wholly visible findings enter detailed
public evidence. Holdout outcomes contribute aggregate counts. Evidence with
unknown visibility is withheld; missing compiler rejection details are not
invented.

Trace citations must match known policy provenance by both identity and span.
The projector uses canonical stored excerpts. Report hashes bind scenario
visibility to the one frozen suite; appending a different suite cannot turn old
holdout cases or finding targets into public evidence. Coverage follows the
latest coverage-bearing artifact in chronology.

The trusted Python revision stage receives the canonical full suite because its
validator checks that suite's digest. Its model adapter must construct a
restricted prompt excluding holdout cases and gold labels/answers. Passing the
full canonical request to the trusted stage is not authorization to serialize
it into a model prompt. Person 2 must finish and verify this adapter boundary;
Task 19's fake tests cannot prove an arbitrary injected planner obeys it.

## Cached replay and remaining integration

Cached replay accepts an explicitly supplied completed record, checks its
envelopes and dependency anchors, requires one immutable frozen suite and
confirmed contract when those artifacts exist, and exposes read/delete only. It preserves
recorded run and manifest identities and assigns a fresh bounded storage TTL.
It does not rewrite hash-bound identities or call live stages. Duplicate stored
IDs are rejected.

There is no recorded production cache yet. The existing completed `RunView`
fixture is authored display data and is not substituted for a recorded run.
Synthetic injected records test replay behavior; Task 21 creates the recorded
demonstration deliverable.

Person 2's asynchronous policy wrappers, Person 3's frozen scenario planner,
Person 4's evaluator/finding/patch/comparison implementations, and Task 20's HTTP
container remain separate integration steps. The existing Person 3 sidecar
adapter does not implement the frozen `ScenarioPlanner` protocol.
