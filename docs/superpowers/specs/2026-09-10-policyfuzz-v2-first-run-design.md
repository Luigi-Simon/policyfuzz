# PolicyFuzz v2 first run

Approved scope: the user's first core milestone, isolated in v2. A user enters
a synthetic policy title, description, personality seed and stakeholder count;
the Orchestrator Agent builds a bound Sandbox request, calls the fixture through
`SandboxService`, validates the result, and returns English public evidence.

## Boundaries

- Exactly four product roles: Orchestrator Agent, Metric Agent, Sandbox Agent,
  Judge Agent. Only Orchestrator and fixture Sandbox execute in this milestone.
- No Metric cases, scored verdicts, Judge reports, policy revisions or live
  MiroFish are represented as implemented.
- Preserve v1 runtime, APIs, generated schemas, archived fixtures and hashes.
- Preserve the friend's `backend/app/v2/sandbox/**` and
  `backend/tests/v2/sandbox/**`, and existing shared Sandbox contract files.
- A synchronous, stateless fixture request is sufficient here. Durable runs and
  live-task scheduling belong to later milestones. No policy text is retained
  by this API after the request or echoed in public output.

## API and interface

Standalone `app.v2.main:app` listens on port 8002. `POST /api/v2/runs` accepts
`{policy: {title, description, agent_seed, agent_count}, fixture_name}` and returns
a typed public Sandbox result. The optional fixture name is `completed` (default)
or `partial_translation_unavailable`; it is an explicit demo control, not a new
policy input. `GET /api/v2/health` reports fixture mode.

The Orchestrator generates new request/run IDs, version `1`, hashes the exact
description without trimming, and passes the exact personality seed and count.
Context and scenario setups are empty; test budget 8 is reserved and does not
claim tests ran. Results must match the complete request fingerprint, identities,
counts, English display requirements and fixture mode before public projection.

Input limits: English title (1–200 characters), description (1–50,000), personality
seed (1–2,000), strict integer count 1–100. Whitespace-only strings are rejected.
Supporting documents are not accepted in this four-field milestone. Public errors
are fixed English messages; input text and adapter exception details are excluded.
Adapter execution has a bounded timeout. Invalid adapter results fail closed.

Public response model and generated artifacts live separately in
`contracts/v2-app/`; `original_records` is absent and extra fields are forbidden.
Frontend types are generated from the v2 OpenAPI file. Runtime schema validation
rejects malformed responses, including backend-only original records.

## Frontend

`/v2` and `/v2/` select an additive React screen. Other paths retain the original
entry and query handling. `/api/v2` is proxied to port 8002 before the v1 proxy.

The screen offers the four inputs, an explicit complete/partial sample control,
submission state, safe errors and retry. It presents Synthetic fixture prominently
and states that the authored dialogue does not analyse the submitted policy or
personality seed. It shows status, requested/configured/observed counts, personas,
messages, translation status, replies, source evidence, limitations and trace IDs.
Partial translation displays the exact unavailable placeholder, never raw text.
New runs clear stale evidence. Abort/unmount cannot restore obsolete results.

## Verification and handoff

Focused backend tests cover exact request binding, complete/partial output,
counts, malformed input, result tampering, timeout/adapter errors and original
record exclusion. Frontend tests cover form submission, safe errors, complete and
partial rendering and response rejection. Verify in a real browser against the
standalone API, and run existing regression/build/generated checks.

Publish to `p1/feat-v2-core` with a draft PR into `p1/feat-policyfuzz-v2`.
Friend continues independently on `p3/feat-v2-sandbox` using the unchanged protocol.
