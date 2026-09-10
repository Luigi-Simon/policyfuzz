# Friend — PolicyFuzz v2 Sandbox Agent handoff

## Your assignment

Own the **Sandbox Agent**: MiroFish integration, stakeholder personas, simulation capture, parsing and English output.
Simon owns Orchestrator Agent, Metric Agent, deterministic tests, app, shared schemas and Judge integration. You may also implement Judge on its separate branch; see ../v2-judge/HANDOFF.md.
There are exactly four top-level agent roles. Translation and parsing are tools; MiroFish stakeholders are participants inside the Sandbox Agent.

Your branch is **p3/feat-v2-sandbox**.
Open your pull request against **p1/feat-policyfuzz-v2**, not main.
Read root AGENTS.md, docs/v2/README.md, team/v2-sandbox/AGENTS.md,
backend/app/v2/sandbox/AGENTS.md and backend/tests/v2/sandbox/AGENTS.md first.

## Files you own

- backend/app/v2/sandbox/**
- backend/tests/v2/sandbox/**

Implement the live adapter in backend/app/v2/sandbox/service.py as MiroFishSandboxService, with async run(request) returning the shared SandboxResult.
Read app.v2.contracts and app.v2.protocols for the exact types.
Do not edit shared models, frontend, API routes or root dependencies independently. Send proposed dependency and contract changes to Simon.

Useful existing reference code:
- engine/app/services/mirofish_bridge.py
- engine/app/services/mirofish_runner.py
- engine/tests/test_mirofish_bridge.py
- engine/tests/test_mirofish_runner.py

Port reusable bridge/capture logic into your owned namespace. The old engine remains available during migration.

## What you receive

A versioned request containing run/request identity, the exact policy text and hash, personality seed, supported stakeholder count, explicit context and optional scenario setups.
You receive scenario circumstances, not expected test verdicts.
The request fingerprint binds all supplied settings, so preserve it in the result.
Read the generated JSON schemas/examples in contracts/v2 and run the foundation check before coding.

## What you return

A typed SandboxResult with:
- Matching request/run/policy identity and full-request fingerprint.
- Correct live execution mode and completed/partial/failed/cancelled status.
- Requested/configured/observed participant counts.
- Stable stakeholder and message IDs.
- English display text and translation status.
- Original source evidence kept internally.
- Ordering and reply/timing references where supported.
- Structured errors/limitations if evidence is incomplete.

You do not produce authoritative policy pass/fail scores or the final policy recommendation. The deterministic test runner and the separately implemented Judge Agent own those.

## Implementation order

1. Run the existing contract fixtures and tests.
2. Add your transport behind a fake MiroFish client and test response parsing.
3. Generate personas from the seed independently from Metric test cases; do not give them a mission to prove a finding.
4. Implement bounded launch/poll/cancel behaviour. Resume a known job on safe retries instead of silently launching duplicates.
5. Capture posts/replies/actions with stable author/source mapping. Preserve unknown metadata as unknown.
6. Add English output handling and safe partial results.
7. Demonstrate one small real run and record the exact setup, counts, mode and limitations.
8. Open the Sandbox PR for Simon's integration.

## English output rules

- Request English in supported upstream prompts. An internal language setting does not imply an undocumented MiroFish API option exists.
- Parse before translation. Translate only human-readable text and generated display labels.
- Never translate IDs, timestamps, metric values, verdict codes or reply relationships.
- Preserve original text/source references internally, alongside the English projection.
- Missing/failed translation gets an English unavailable placeholder and partial status. Never fall back to raw Chinese in the public result.
- Keep stable English display names mapped to original stakeholder identities.
- Cover mixed-language output, malformed data, timeout, unchanged Chinese, and eligibility/negation/limit meaning in reviewed examples.
- The shared Han-text guard is a last check, not a translator or a complete language detector.

## Evidence and counts

Do not derive the number of stakeholders from the number of tests.
Respect configured caps and report actual differences.
Deduplicate repeated delivery of the same source message, not merely identical text from different speakers.
A comment count is not proof of a validated conversation graph.
Do not invent missing reply links or timestamps.
A new policy version must start a new version-bound capture; never reuse the old policy's conversation as revised evidence.

## Tests and handoff

Use fake transports in tests; no real provider calls in automated tests.
Cover identity/hash mismatches, duplicate IDs, unknown speakers, partial/failed/cancelled runs, English fallback and immutable metadata.
Return the exact commit, changed files, setup commands, dependency requests, test outputs and a small live sample with mode clearly labelled.
Do not send credentials in chat, documents or commits.

## First success condition

Simon submits one policy. Your adapter returns a real English conversation. His Judge Agent cites a specific returned message by ID. This is the first integration milestone; the full policy test/revision engine is Simon's work.
