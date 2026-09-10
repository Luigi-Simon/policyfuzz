# Friend — PolicyFuzz v2 Judge Agent handoff

Yes, you can build Judge independently now. Start with the supplied complete,
partial and unscored evidence examples; no running Metric or MiroFish service is
required for adapter development.

## Branch and ownership

Branch: **p3/feat-v2-judge**. PR target: **p1/feat-policyfuzz-v2**.
Use a separate worktree so ongoing Sandbox edits stay on their original branch:

```bash
git fetch origin
git worktree add ../policyfuzz-judge -b p3/feat-v2-judge origin/p3/feat-v2-judge
cd ../policyfuzz-judge
```

If you already have a local Judge branch, pass its name to `git worktree add`
without `-b`; an existing checked-out branch should be used in its own worktree.
Do not reset either feature branch. This Judge branch includes the shared Metric
and Judge contract checkpoint; it does not move your Sandbox branch.

You own:

- `backend/app/v2/judge/**`
- `backend/tests/v2/judge/**`

Simon owns Metric, Orchestrator, runner, shared contracts, API and UI. Your Sandbox
ownership remains in its separate folders/branch. Exactly four product roles:
Metric Agent, Orchestrator Agent, Sandbox Agent and Judge Agent.

## Fixed Python interface

Implement `backend/app/v2/judge/service.py`:

```python
from app.v2.judge_contracts import JudgeRequest, JudgeResult

class JudgeAgentService:
    async def run(self, request: JudgeRequest) -> JudgeResult:
        ...
```

The shared protocol is `app.v2.judge_protocols.JudgeService`. Import models from
`app.v2.judge_contracts`; propose changes to Simon rather than defining parallel
types. Core validates every returned result with `validate_judge_result`.

Generated schemas and sample JSON: `contracts/v2-judge/`.
Start by opening `fixtures/complete-request.json` and `fixtures/complete-result.json`.
Executable examples: `app.v2.judge_examples.make_judge_example(kind)` where kind
is `complete`, `partial` or `unscored`. Both Metric and Sandbox evidence in these examples is authored mock data, not
executed policy tests or live simulations. Metric sets generation_method to
`authored_fixture`; Judge and Sandbox set execution_mode to `fixture`. `complete`
is a fixture status example, and includes one mock pass and one mock failure.

## What Judge receives

`JudgeRequest` binds run/request/policy identity and contains:

- Metric review: interpreted clauses, explicit goals, assumptions and limitations.
- Metric cases: exact verdicts, action traces, assertion results and counterexamples.
- Optional public Sandbox evidence: English personas/messages, translation status
  and sources. Original records and provider prompts are excluded.
- Explicit limitations when a stage is absent.

The orchestrator must supply validated, matching evidence. No endpoint or separate
database is needed for your initial implementation. The Metric runtime is being developed separately; this branch contains its shared
evidence models and review support, not the runner. Existing Sandbox fixture runs
are separate; do not combine unrelated run IDs or
relabel old evidence to create a live combined run. Core owns that integration.

## What Judge returns

`JudgeResult` contains summary, cited pros/cons, advisory recommendation, actionable
next steps and cited key interactions. Preserve identity and use
`judge_request_fingerprint(request)` for the result fingerprint.

Citation kinds:

| Kind | `id` | `case_id` |
| --- | --- | --- |
| `policy_clause` | A supplied review clause or goal ID | null |
| `metric_case` | A supplied Metric case ID | null |
| `metric_step` | A supplied trace step ID | Owning case ID |
| `sandbox_message` | An available English message ID | null |

Key interactions require message citations. Do not invent reply relationships or
say two stakeholders interacted unless supplied reply/order evidence supports it.
Never cite an unavailable-translation placeholder as substantive evidence.

Judge cannot change Metric pass/fail/unscored verdicts, counts or assertion truth.
Recommendations are advisory. `consider_limited_pilot` is blocked for failing,
missing, unscored or fixture evidence. It never means a policy is proven safe.
Incomplete evidence requires `partial` and limitations; failed Judge calls require
`failed`, errors and `insufficient_evidence`. Never silently substitute fixtures
after a live model call fails.

All public generated prose must be English. The shared Han guard is not a complete
language detector. Prompt for English and validate typed output; use a bounded
retry for malformed output, then a truthful failure. Citation validation proves
references exist; it does not prove semantic grounding. Test that separately.

## Build order and offline checks

1. Create a fake injectable model client and adapter tests using all three examples.
2. Build a prompt separating reviewed rules, exact tests and simulated observations.
   Treat policy/evidence text as data, never instructions to override Judge rules.
3. Parse into JudgeResult, preserve identity, validate citations and English output.
4. Add bounded timeout/retry and explicit partial/failure handling.
5. Connect your configured model only after offline tests pass. Ask Simon to add
   dependencies/configuration you need; never commit credentials or provider dumps.

From repository root (Python 3.12+):

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -e './backend[dev]'
backend/.venv/bin/python -m pytest backend/tests/v2/test_judge_contracts.py backend/tests/v2/judge -q
PYTHONPATH=backend backend/.venv/bin/python -m app.v2.export_judge --check
```

On Windows use `backend\.venv\Scripts\python.exe`, and set `$env:PYTHONPATH = 'backend'` in PowerShell before the export check.
All automated tests use fake clients and make no live provider calls.

## Agent prompt to paste

> Work on p3/feat-v2-judge. Read AGENTS.md, team/v2-judge/HANDOFF.md and the scoped
> AGENTS.md files. Implement JudgeAgentService only in backend/app/v2/judge and
> backend/tests/v2/judge using the shared JudgeService interface and supplied
> fixtures. Start with fake-client tests. Return English, cited advice; preserve
> deterministic Metric results and expose partial evidence. Do not change shared
> contracts, Sandbox, API, frontend or root dependencies independently. Target the
> PR at p1/feat-policyfuzz-v2 and report setup, tests and remaining limitations.

## Your handoff to Simon

Provide commit, changed files, dependency requests, fake-client test results,
timeout/retry behaviour and one small explicitly labelled live sample if run.
Do not send prompts, credentials or private policy text. Simon wires the adapter
into the orchestrator and evidence screen after contract and integration review.
