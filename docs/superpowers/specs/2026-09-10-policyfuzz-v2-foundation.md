# PolicyFuzz v2 parallel-work foundation

This implements the user's approved two-person split. It prepares development branches and a runnable shared boundary; it does not claim the full v2 application or live MiroFish adapter is implemented.

## Required outcome
- Keep remote main and all existing repository history intact.
- Publish integration branch p1/feat-policyfuzz-v2.
- Publish Simon's p1/feat-v2-core and friend's p3/feat-v2-sandbox from the identical verified foundation commit.
- Provide friend-owned Sandbox instructions and Simon-owned core instructions in the v2 repo.
- Expose exactly Orchestrator Agent, Metric Agent, Sandbox Agent and Judge Agent in v2. The old role label Fuzz Agent maps to Metric Agent; PolicyFuzz remains the product name.
- Do not alter v1 schemas, cached evidence hashes, or existing app behavior.

## Architecture
Use the additive app.v2 namespace. Simon owns shared contracts, fixture adapter, orchestrator, Metric Agent, runner, Judge Agent, frontend, public API and shared configuration. The friend owns app.v2.sandbox implementation and its tests. Parsing, translation and deterministic execution are supporting tools, not agent roles.

Canonical imports: app.v2.contracts for v2 data, app.v2.protocols for SandboxService. Existing v1 imports remain unchanged. Versioned JSON schemas and synthetic fixtures live under contracts/v2. No new runtime dependency is needed: Python 3.12, Pydantic 2 and the standard library suffice.

## Boundary
SandboxService is an async Protocol: run(SandboxRequest) -> SandboxResult. It is an internal adapter, not a new public API.
PolicyInput contains title, description, agent_seed and agent_count as required fields, plus optional supporting documents.
Request includes schema version 2.0, request/run IDs, exact policy version/text/title/hash, personality seed, stakeholder count, explicit context, optional scenario setups, English target and bounded round/time settings. Keep test budget separate from stakeholder count and random seed separate from personality seed. ScenarioSetup describes circumstances/actions and contains no expected-verdict field.
Result echoes request/run/policy identity and a fingerprint of the complete request. It contains live/recorded/fixture mode; completed/partial/failed/cancelled status; requested/configured/observed counts; personas; ordered English messages; source evidence references; reply references when available; and structured limitations/errors.
Backend-only original records are kept distinct from an allowlisted public projection. Public results must not leak original text. Stable record and speaker IDs cannot change during translation. An English placeholder plus partial status handles unavailable translation.
Validate unique persona/message/source IDs, author/source references, policy text hash, response/request binding, sensible counts, missing/duplicate reply references and failure/completion contradictions. Completed requires nonempty evidence; fixture results must always identify themselves as fixture. English display fields reject remaining Han text, explicitly documented as a script guard rather than proof of English fluency or faithful translation.
No provider/model calls occur in this foundation or its tests.

## Deliverables
- Executable Pydantic contracts, async protocol, safe public projection and request/result validation.
- Clearly labelled fixture Sandbox service, supporting completed and translation-unavailable partial examples.
- Generated request/result/input JSON schemas, role labels and deterministic fixtures; check for drift.
- Offline smoke command and unittest cases. Tests must fail before implementation and exercise actual provenance/privacy/count/status behavior.
- Scoped ownership AGENTS.md, two copyable AI-agent handoffs, setup commands for Windows and macOS/Linux, integration acceptance checks and a clear remaining-work checklist.
- A small CI foundation job. Existing CI and v1 code are preserved.
- Remote commit/branch verification and links for both people.

## Scope boundary and decisions
A live MiroFish implementation belongs to the friend's branch. Real translation and the complete Metric/Orchestrator/Judge workflow belong to the next development work packets. A fixture is never silently substituted for live execution. The current source snapshot is accessed through the authorized GitHub connector; changed files will be committed against the actual remote base tree/parent so untouched files and history remain intact.

