# Deterministic evaluator handoff

Status: implementation complete for Tasks 5–7, 16–18 evaluator runtime and Person 4 development/control corpus. Metrics/scorer/CLI were explicitly transferred by Person 1 to the audit worker and integrate through the frozen contracts. No blind material was opened and no blind/manual-review evidence was fabricated.

## Public interfaces

- `app.features.evaluation.engine.DeterministicEvaluationEngine.evaluate(EvaluatePolicyRequest) -> EvaluationReport`, `ENGINE_VERSION = "1.0.0"`.
- `app.features.evaluation.findings.DeterministicFindingAnalyzer.analyze(AnalyzeFindingsRequest) -> FindingReport`.
- `app.features.evaluation.patches.DeterministicRevisionApplier.apply_revision(ApplyRevisionRequest) -> PatchApplicationResult`; invalid proposals return an explicit failure result atomically.
- `app.features.evaluation.regression.DeterministicRegressionAnalyzer.compare(CompareRevisionRequest) -> ComparisonBundle`.
- `app.features.evaluation.metrics.compute_metrics(MetricsRequest) -> MetricsReport` is the transferred worker's frozen callable.
- Low-level helpers live in `predicates`, `rule_validation`, `resolution`, `compliance`, `assertions`, `signatures`, and `findings`; local predicate/rule trace dataclasses are not competing public protocols.

The engine source commitment must include assertions, compliance, engine, errors, findings, metrics, patches, predicates, regression, resolution, rule_validation, and signatures. Manifest ownership remains Person 1.

## Behavior and boundaries

Execution validates policy/contract/suite anchors, rejects unsupported engine versions and invalid policy graphs, evaluates every predicate, resolves all five dimensions in enum order, and preserves independent compliance. Matching unsupported clauses produce INCONCLUSIVE. Equal survivors coalesce; conflicting survivors remain CONFLICT. Invalid scenario data becomes an ERROR trace.

Findings group witnesses deterministically and do not treat unasserted allowance as a loophole. Missing coverage inside an existing dimension is a structural gap. An entirely absent effect dimension required by a confirmed invariant is a witnessed intent omission; the duplicate invariant-only structural gap is suppressed. Confirmed invariant FAIL also produces intent breach. Candidate unsupported findings stay unscored.

Revision validation reconstructs baseline findings deterministically because the frozen apply request has no finding report. Explicit session acceptance remains the coordinator's boundary: the proposal carries accepted IDs, and the applier rejects unknown, candidate, or private witnesses. It verifies all anchors, bounds operations/rules, rejects impossible conditions, unrestricted catch-alls, semantic no-ops and unrelated dimensions, preserves IDs, increments revised rule revisions, and assigns session provenance. One source rule can be changed once in a proposal; use replace_rule to add multiple edges to that source.

Comparison recomputes deterministic reports and checks supplied finding evidence while allowing coordinator-applied review/severity metadata. It compares every scenario/dimension and assertion pair, protects held-out/protected cases, checks unrelated rules and exact confirmed operation contents, and combines all seven gates. Equal bad-state totals cannot conceal relocation.

## Corpus and evidence

`build_benchmarks.py` deterministically rebuilds the six owned artifacts from P2's source fixtures. Each suite has exactly 15 independently authored gold scenarios. `expected-effects.json` is an exact frozen `EvaluationReport` recording expected baseline execution; independent intended values are the gold assertions in the suite. Strict frozen models preclude extra banner fields; banners appear in policy text and supported suite/benchmark identifiers.

Development has exactly three scored roots (receipt boundary gap, international hotel approval conflict, omitted daily meal intent) plus one unscored unsupported-language candidate. Corrected control has zero scored roots. Both achieve required rule/invariant coverage. The three-operation development correction passes all seven acceptance gates on the identical suite.

- Development suite: `c988053930f1a6e6b12a3a059ad2c630576138482ce9757fddcbd7af7a480c94`.
- Corrected suite: `a8da764114e6407f3dfdf33337db78eff9b8281d14ac14e116f71652f281b9e2`.
- Development score: 3 true positives, 0 false positives, 0 false negatives (100% precision/recall/F1).
- Corrected score: 0/0/0; precision/recall/F1 N/A.
- `evidence/{development,corrected-control}-{score,replay}.json` preserves exact public score/replay evidence; each replay contains exactly three identical semantic execution hashes.

## Verification

Meaningful RED/GREEN cycles covered missing execution modules, missing findings/revision modules, missing comparison module, missing corpus, catch-all rejection, forged finding rejection, and confirmed-operation mismatch. Additional endpoint/override/compliance checks cover numeric boundaries and chains.

- Owned focused execution/findings/revision/regression/corpus tests: **64 passed**.
- Final full evaluation suite including metrics/scoring/CLI: **73 passed**, **84% statement coverage**.
- Ruff on all owned runtime modules, tests, and benchmark generator: **all checks passed**.
- Three identical semantic evaluations for each public benchmark: passed.
- Exact public benchmark scoring against manifest: passed.

## Limitations

Frozen models supersede older plan names: they expose PredicateResult/EvaluationTrace rather than public PredicateTrace/RuleTrace; statuses rather than state/value conveniences; EvaluationReport has no execution_sha256; MetricsReport has fixed counts/percentage fields rather than arbitrary metric ratios. Replay hashes the frozen report's semantic projection. Full artifact input hashes remain significant integrity commitments.

PolicyIR itself rejects any aggregate override cycle, even one spanning separate dimensions; feature validation also walks each dimension separately but cannot weaken frozen model validation. Source text/quote verification belongs to compilation because EvaluatePolicyRequest does not contain the original document. The engine cannot independently recompute an opaque engine/manifest digest without those payloads; the workflow verifies those commitments.

Blind scoring/ten-minute independent human comparison is deferred to the authorized sealed reveal procedure. No Git mutations, commits, or pushes were made by this worker.

## Round 1 review follow-up

All four Important review issues are fixed. Target acceptance now requires actual resolution and independently asserted success for every original witness, preserving all seven gates against fingerprint changes. Replacement override deltas remain inside accepted conflict dimensions/endpoints; unaccepted precedence remains unchanged. Hintless clauses affect only required dimensions; explicit matching and empty hints remain applicable.

The original analyzer-derived defect answer key was not independent scoring evidence. It has been replaced by explicit independently authored source/intent/witness definitions, assembled into the manifest before evaluation and then measured without alteration. Three corruption tests prove changed analyzer fingerprints, witnesses, or targets cannot change the answer key or produce published evidence. Regeneration independently confirms development3/0/0 and corrected0/0/0; suite hashes/proposal anchors are unchanged. See `evidence/*-label-validation.json` for definition/manifest commitments.

Final round verification: **83 evaluation tests + 3 concrete workflow checks passed**; changed-file Ruff check/format passed. No Git or provider actions. The implementation report contains the exact reproductions and changed paths.

Person 1 additionally granted the minimal CLI interface fix: select exactly one session-confirmed compiled baseline from real records containing an earlier provisional policy, reject conflicting confirmed baselines, and preserve the first raw findings over later review metadata. Two real-record tests cover selection and rejection. Final evaluator suite: **85 passed**; all seven changed code/test/builder files pass Ruff check and format-check. No further edits pending.

## Explicit post-run gold assessment and final normalized fixtures

Added deterministic `gold_assessment.assess_gold` and CLI `assess-gold` without changing frozen public schemas, strict `score_benchmark`, metrics, or online execution. Normal workflow discovery freezes model-generated cases (commonly 10–15) whose IDs and complete confirmed contract can differ from the independently sealed 15 gold cases. Strict `score` correctly refuses those mismatched evidence sets. The first-run discovery headline gate therefore remains **unmeasured**; this new command cannot satisfy Gate B.

Command (after authorized reveal only):

```sh
PYTHONPATH=backend backend/.venv/bin/python -m app.features.evaluation.benchmark_cli assess-gold \
  --run-result RAW.json --run-metadata RAW.json.metadata.json \
  --benchmark-dir REVEALED_DIRECTORY --schema-seal blind-schema-seal.json \
  --output NEW_DIRECTORY
```

The command validates the immutable original record, recorder byte/payload commitments, recorded source, schema seal binding, all seven sealed artifact hashes and anchors, source quotes, original deterministic replay, and exact current engine source commitment. It evaluates the captured session-confirmed baseline on a new explicitly derived gold suite/contract; the canonical gold policy is used for sealed artifact validation and is never substituted for the captured policy. Gold labels, case IDs, facts, and assertions remain unchanged; unmatched roots count as legitimate false positives/false negatives under the unchanged strict matcher.

Publication atomically creates one exclusive directory containing `score.json` and `provenance.json`. Both explicitly state `headline_gate_eligible: false` and `first_run_discovery_measured: false`. The score is wrapped as a post-run gold-assisted assessment, so it cannot parse as a bare BenchmarkScore. Provenance includes original and derived commitments plus reproducible captured policy, gold contract, derived suite, evaluation, and findings. Original raw records are never edited. Atomic no-replace publication supports Linux/macOS and fails closed where unsupported.

RED/GREEN: the new test module first failed because the implementation was missing; nine focused tests now cover untouched raw bytes, distinct captured/canonical policies, strict unmatched-root FP/FN counts, tampered seal/member/raw/engine rejection, missing confirmed baseline, exclusive output, and injected publication failure with no partial artifact pair. All tests use synthetic authored artifacts and fake recorder metadata; no private blind archive or live provider was accessed.

After P2 source identity normalization, reran the independent public builder and refreshed all six public artifacts plus six owned score/replay/label evidence files. Independent label definitions were unchanged. Development suite SHA is `c988053930f1a6e6b12a3a059ad2c630576138482ce9757fddcbd7af7a480c94`; corrected-control is `a8da764114e6407f3dfdf33337db78eff9b8281d14ac14e116f71652f281b9e2`. These supersede earlier suite hashes. Development remains TP3/FP0/FN0; control remains TP0/FP0/FN0. Three identical semantic replays produce development `b6f9faa63787ef0931b08fa7a9800ce66371f1eca8bd76a9209609d31f319111` and control `c69338d678129e0468a47ee6adf2d832db177452f5339c194bde2beb14f533e9`. Both exact expected-effects reports pass workflow validation. P2 received fresh suite/finding anchors for its owned revision fixture.

Final checks: `backend/.venv/bin/python -m pytest backend/tests/features/evaluation -q` → **94 passed in 4.05s**. Ruff check and format-check pass for `gold_assessment.py`, `benchmark_cli.py`, and `test_gold_assessment.py`. No Git mutations, shared schema edits, scorer/metrics changes, private blind reads, or provider calls. Root owns final integration verification, README/Gate B behavior, and review. Edits stopped for root review.
