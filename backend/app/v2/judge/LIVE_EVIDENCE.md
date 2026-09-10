# Judge implementation handoff — 11 September 2026

Branch: `p3/feat-v2-judge`. Integration target: `p1/feat-policyfuzz-v2`.
Base checkpoint: `2a887b5`. The commit containing this note carries the implementation; use `git log -1` for its ID. No PR or push was performed.

## Offline verification

Run from `backend/` with Python 3.12:

```bash
python -m pytest tests/v2/test_judge_contracts.py tests/v2/judge -q
python -m pytest tests/v2 -q
python -m ruff check app/v2/judge tests/v2/judge
python -m app.v2.export_judge --check
```

Final result: **99 Judge contract/adapter tests**, **156 total v2 tests plus 2 subtests**, clean scoped lint, and matching generated shared schemas. All tests use fake clients; none call a provider.

The broader backend run earlier in development had 1,676 passes and two failures. The local HTTP smoke test then passed with loopback-port permission. The remaining failure is the existing `test_script_entry_point_runs_from_outside_repository`: `scripts/package_submission.py:22` cannot import `scripts.verify_submission` when launched outside the repository. The same error was independently reproduced using the unmodified checkpoint script in a temporary directory. Neither the script nor its test was changed; it is outside Judge ownership.

## Live provider evidence

The live checks used the existing `gpt-4o-mini` configuration and OpenAI strict JSON-schema output. Credentials were read from the existing local environment configuration and were never copied into this branch. Only the supplied synthetic Judge examples were sent. No Metric runner or MiroFish simulation was launched, and unrelated Sandbox runs were not combined.

`live-sample.json` is the **final complete-example result**, bound to `contracts/v2-judge/fixtures/complete-request.json`. Judge execution is `live`; input Metric cases are `authored_fixture` and Sandbox dialogue is `fixture`.

This final attempt used `max_repairs=2`, a 120-second deadline, and six provider calls. It returned **failed / insufficient_evidence** after the reviews reported unsupported claims, Metric contradictions, and missing limitations. It contains no findings or next steps. This demonstrates the failure boundary, not successful policy analysis. Earlier development versions returned completed drafts; manual inspection found overly broad wording, which led to stronger prompts, explicit mock labels on individual findings, and targeted repair feedback. Those earlier drafts are not the final sample.

The saved result is public, typed output only. Prompts, raw provider responses, private review feedback and credentials are not included. Model-review issue codes are retained in the sanitized failure result to make the failure actionable.

`live-unscored-sample.json` separately matches `contracts/v2-judge/fixtures/unscored-request.json`. It used the default repair/deadline settings and also returned **failed / insufficient_evidence** after the model review reported English, grounding, limitation and provenance issues. These are reviewer reports, not independently established defects in each draft. The sample demonstrates truthful refusal to publish unaccepted advice; successful live missing-evidence advice remains unverified.

## Ready for integration / remaining work

- Public entry point: `app.v2.judge.service.JudgeAgentService.run(JudgeRequest) -> JudgeResult`, asynchronously. Setup and client ownership are documented in `README.md`.
- Owned implementation: `__init__.py`, `client.py`, `evidence.py`, `prompts.py`, `schema.py`, `service.py`; tests: `backend/tests/v2/judge/conftest.py`, `test_client.py`, `test_guardrails.py`, and `test_service.py`. Documentation and synthetic live samples are in the Judge folder.
- Dependency requests: none. Shared schemas, Metric, Orchestrator, Sandbox, API, UI, and root settings are unchanged.
- Defaults: one shared format/semantic repair, at most four provider calls, 90-second overall deadline, no SDK retries or automatic fixture fallback. Core may explicitly configure two repairs; it does not relax validation.
- Core must supply validated, matching evidence and wire the result into its workflow and UI. Intentional single-stage runs remain partial under the current shared contract.
- **Live advisory quality remains unproven with the configured model.** Before treating this as a reliable successful analysis path, evaluate a suitable model and several policy-specific synthetic inputs, including adversarial and incomplete evidence. Reviewers can miss a bad claim or reject valid advice; fake tests verify the enforcement mechanism, not general model accuracy. Do not describe this sample as a live combined policy evaluation.
