# Semifinal prototype refinement — 2026-09-09

This pass hardens the existing PolicyFuzz workflow and optional MiroFish integration
on top of `61cd0d5946d78202493f89b2e733956ce478ebcb`. It preserves the version `1.0`
core contracts and distinguishes deterministic policy evidence from independent
exploratory simulation. It does not establish perfect operation or final release
acceptance.

## Reliability improvements

- Confirmed simulation launches now read the actual `PolicyDocument.pages` text.
  Existing contract, stage and artifact-hash checks still gate the launch.
- Synchronous sidecar calls run outside the core API event loop, keeping health and
  other requests responsive during a simulation. Bounded waits, safe service errors
  and client cleanup cover connection, timeout, constructor and cleanup failures.
- Frontend simulation requests have cancellation and generation guards. Reset,
  deletion, a new run or an unmounted view cannot be overwritten by a late result.
  A failed deletion preserves the current evidence.
- Run identifiers are retained in the URL so a refresh can reopen available core
  and simulation results. Invalid or partially populated responses produce a safe
  message instead of crashing the evidence view; valid failed runs retain their ID.
- Simulation controls validate the seed and whole-number population. Mock mode has
  no unsupported simulation action, and bundled samples explain why pasted text is
  needed. A core failure stays visible; an independent continuation is explicit.

## Evidence improvements

The optional engine now rejects invalid live extraction, unsupported output and
inexact citations. It validates the complete quoted text and page against the
source, preserves source whitespace and rejects input beyond its supported prompt
limit instead of silently truncating it. Disabled-model heuristic output remains
explicitly unverified demo output.

Exploratory generation uses a stable seed across Python processes and distributes
cases across rules before repeating them. It no longer invents expected outcomes.
Cases without independent assertions remain unasserted and are shown as **Not
scored**. Model explanations and swarm activity cannot overwrite or inflate the
engine's heuristic score. Conversation observations remain candidate evidence;
they do not change the core deterministic verdicts.

Structured revisions are applied to an isolated candidate and reevaluated with the
same scenarios. A failed revision retains the previous policy and evidence. Prior
captures are archived and removed from active scoring when policy, suite or swarm
state changes. Comparisons remain labelled exploratory, and drafted wording remains
unverified. MiroFish launch is blocked after a structured revision because the
retained original prose cannot represent the revised rules; local same-suite
evaluation remains available.

The API marks simulation output as `independent_exploratory_simulation` with
`frozen_suite_reused: false`. Confirmed launch hashes identify the source decision;
the sidecar interprets the original document and generates its own cases. The UI
also explains that MiroFish retains a separate copy and that deleting a core run
does not delete the external simulation.

## Startup and ownership

After installing the documented dependencies, `npm run dev` starts the cached core
API and HTTP frontend together. `npm run dev -- --mock` starts the labelled frontend
rehearsal, and `npm run dev -- --agents` additionally starts the optional engine
from `engine/.venv`. The latter does not start the external MiroFish project. The
launcher checks prerequisites and shuts down its child services together.

Root CI now runs the optional engine's tests as well as the existing application
checks. Shared models, generated OpenAPI, fixtures and scoped ownership instructions
remain intact. The user authorized this refinement across all five workstreams;
ongoing team ownership remains as documented in each `AGENTS.md`.

## Verification and limits

The exact commands and results are recorded in
[`semifinal-verification-2026-09-09.json`](../team/person-1-integration/evidence/semifinal-verification-2026-09-09.json).

- Backend: **1,534 tests passed**, including ten focused simulation API tests.
- Optional engine: **83 tests passed** after the final independent review fixes.
- Frontend: **177 tests passed**; generated-type drift, type checking and production
  build passed.
- All **111 public schemas**, OpenAPI and canonical fixtures remain unchanged.
- The scripted workflow removes **three defects to zero** using the same frozen
  **ten-case suite**. Three replay executions match.
- The combined launcher served both backend health and the frontend over HTTP and
  shut down successfully. This checks startup, not a complete browser journey.
- Independent review found two additional blockers—nullable failed-run artifacts
  and simulation launch against stale prose after revision. Both were fixed and
  their focused regressions passed.

All provider responses in this pass were fake, scripted or cached; there were
**zero real provider calls**. A supervised frontend preview started, but browser
control stalled. No browser acceptance, screenshot, fresh live-provider rehearsal
or external MiroFish swarm acceptance is claimed.

Historical live evidence is retained in the
[Person 2 live handoff](../team/person-1-integration/live-extraction-handoff.md).
The independent human reviews, sealed blind attempt and measurement limitation,
Gate B, release freeze and final media remain separate pending gates in
[implementation status](implementation-status.md).
