# PolicyFuzz version 1.0 contracts

Person 1 owns these generated interfaces. Task 4 freezes version `1.0`.
The source is `backend/app/domain/models`; generated files must not be edited
by hand. The current registry contains 111 concrete model schemas, an OpenAPI
registry, and one completed `RunView` fixture.

Read [Task 4 integration](task4-integration.md) for exact protocol signatures,
LLM request fields, provisional suggestions, configuration, retries and the
Person 2 handoff. [freeze-v1.json](freeze-v1.json) records source/artifact hashes
and the verified scope, including tested runtime versions. The manifest is not a dependency lockfile. Its `freeze_sha256` is the canonical hash of the record
with that self-hash field omitted. File hashes cover exact bytes.

Shared interface changes require Person 1 review, regenerated schemas and a
new verified freeze record. Breaking changes require an explicit versioned
migration. The initial Task 4 freeze preserves the seven-operation HTTP contract
and canonical completed fixture. Fake-tested provider mapping is included;
live provider/model compatibility and later feature/API wiring remain separate
gates.

## Generate and check

Run from `backend` with its virtual environment:

```bash
.venv/bin/python -m app.domain.export_schemas --output ../contracts/jsonschema
.venv/bin/python -m app.domain.export_schemas --openapi ../contracts/openapi.json
.venv/bin/python -m app.domain.contract_fixtures --output ../contracts/fixtures/run-view.completed.json
.venv/bin/python -m app.domain.export_schemas --check ../contracts/jsonschema --openapi ../contracts/openapi.json
.venv/bin/python -m app.domain.contract_fixtures --check ../contracts/fixtures/run-view.completed.json
```

Check mode does not write. It fails for missing, changed, or extra generated
schemas and for OpenAPI/fixture drift. Generation preserves non-schema files.
Windows users can use `.venv\Scripts\python.exe` in these commands.

## HTTP registry

`openapi.json` describes seven operations; it does not start the application.
Task 20 must align FastAPI's components, status codes, and error wrapper with it.

| Operation | Request | Success |
| --- | --- | --- |
| `POST /api/v1/runs` | `CreateRunRequest` | `202 CreateRunResponse` |
| `GET /api/v1/runs/{run_id}` | Path ID | `200 RunView` |
| `POST /api/v1/runs/{run_id}/confirm-contract` | `ConfirmContractRequest` | `200 RunView` |
| `POST /api/v1/runs/{run_id}/select-findings` | `SelectFindingsRequest` | `200 RunView` |
| `POST /api/v1/runs/{run_id}/confirm-revision` | `ConfirmRevisionRequest` | `200 RunView` |
| `DELETE /api/v1/runs/{run_id}` | Path ID | `200 DeleteRunResponse` |
| `GET /api/v1/health` | None | `200 HealthResponse` |

Declared application errors use `{ "error": PublicError }`. Public comparison
data includes the five aggregate assertion-transition buckets and all seven
patch checks. Individual holdout assertions and private benchmark models do
not enter `RunView`.

## Hashes and envelopes

Use `app.core.hashing.canonical_sha256` for structured values. It produces
SHA-256 over compact, sorted-key UTF-8 JSON with NFC-normalized strings and
keys. It preserves sequence order, sorts normalized sets, and handles typed
models, enums, UUIDs, and aware UTC timestamps. Floats, bytes, naive timestamps,
unsupported objects, cycles, non-string keys, and normalized key collisions
are rejected. Booleans remain distinct from integers.

`app.core.artifacts.make_artifact_envelope` validates typed payloads and
references, stores sorted unique parent artifact hashes, and computes complete
and semantic payload digests. `validate_artifact_envelope` recomputes both.
Envelope metadata and parent contents are not covered by those payload digests.
Parent objects require separate verification.

Projection tables omit only named self-digests on their concrete models, such
as suite content and embedded trace digests. Input anchors, source/quote hashes,
reference hashes, IDs, revisions, and decision data remain significant.
Semantic projection additionally omits named timestamps, confidence, event
logs, and presentation fields. It is distinct from the stretch prose-equivalence
signature. Unknown future fields remain significant until explicitly reviewed.

ZIP bytes, exact source text, and exact quotes use ordinary SHA-256 of their raw
UTF-8 bytes (ZIPs are already bytes). These preserve the earlier custody and
citation commitments; they are not hashes of JSON string representations.

## Completed fixture

`fixtures/run-view.completed.json` is explicitly authored synthetic display
data in `cached` mode. It contains all six effect states, five aggregate
assertion-transition categories, exact citations, and seven patch checks. It
demonstrates a rejected patch with consistent regression counts.

Its input hashes identify fixed, labeled illustrative anchor dictionaries.
It is not evidence of a model call, engine evaluation, or benchmark performance,
and it is separate from the later recorded cached-run deliverable.

## Schema-bound benchmark package

The validator is tooling for Person 5's separate Gate A2. Task 3 does not open,
approve, or reseal the actual private benchmark. The existing late-seal and
pending-human-review disclosures remain in force.

The external ZIP contains exactly seven plain-JSON members:

| Member | Model |
| --- | --- |
| `source-labels.json` | `BenchmarkSourceLabels` |
| `canonical-policy-ir.json` | `PolicyIR` |
| `confirmed-contract.json` | `PolicyContract` |
| `frozen-suite.json` | `ScenarioSuite` |
| `expected-effects.json` | `EvaluationReport` |
| `defect-manifest.json` | `BenchmarkManifest` |
| `corrected-semantics.json` | `BenchmarkCorrectedSemantics` |

Source labels embed `PolicyDocument`. Source text is reconstructed by joining
page text in order with contiguous offsets and no inserted separators. Corrected
semantics contain expected rule content without invented citations or session
approval provenance. They are not an applied `PolicyIR` revision.

From the repository root, the custodian runs:

```bash
backend/.venv/bin/python scripts/validate_and_seal_blind_contracts.py --archive ../policyfuzz-blind-schema-private.zip --source-seal submission/evidence/blind-seal.json --defect-ids-file ../policyfuzz-blind-defect-ids.json --output submission/evidence/blind-schema-seal.json
```

The private archive and defect-ID file stay outside the repository; the public
source seal may be the committed repository file. The validator requires 8–10
baseline rules, 15 scenarios, three unchanged defect IDs, and a protected normal
case. It checks schemas, exact source spans, hashes, and cross-references without
running an evaluator or judging the expected answers' semantic correctness.

The source seal's archive hash remains the Gate A1 identity. Source and defect-ID
hashes must match it; its old manifest byte hash is not compared with the newly
shaped schema-bound manifest. Contract identity is bound through suite and
manifest hashes, since `PolicyContract` has no direct document/rule-set fields.

ZIP input is limited to 8 MiB, individual expanded members to 2 MiB, total
expansion to 8 MiB, metadata files to 64 KiB, and source text to 50,000 characters.
Members are read in memory without extraction. Failure messages contain safe
codes. Successful output contains only hashes, schema version, counts, time,
and custodian role; an existing output file is never overwritten.
