# PolicyFuzz v2 Parallel-work Foundation Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for implementation and independent review. The user has authorized execution and creation of v2 work branches.

**Goal:** Let Simon and his friend independently build their v2 components against one tested Sandbox contract.

**Architecture:** Add app.v2 contracts and a fixture adapter without changing the v1 application. Publish a shared foundation followed by two independent work branches.

**Tech Stack:** Python 3.12, Pydantic 2, standard-library unittest; existing GitHub Actions.

**Spec:** docs/superpowers/specs/2026-09-10-policyfuzz-v2-foundation.md

## Global Constraints
- Exactly four roles: Orchestrator Agent, Metric Agent, Sandbox Agent, Judge Agent.
- Keep main unchanged and preserve Git history; never force-push.
- The friend's owned paths are backend/app/v2/sandbox/ and backend/tests/v2/sandbox/.
- Simon owns shared contracts, configuration and all other v2 components.
- No live provider requests in tests. Fixture results must be labelled.
- V1 schemas and historical evidence remain unchanged.
- Use English public display fields and preserve original evidence only internally.

## Task 1: Executable boundary and fixture
Files: backend/app/v2/contracts.py, protocols.py, fixtures.py, export_contracts.py, __init__.py; backend/tests/v2/test_sandbox_contract.py; contracts/v2/*.
Consumes: the spec's SandboxRequest/SandboxResult requirements.
Produces: async SandboxService.run(request), FixtureSandboxService.run(request), validate_sandbox_result(request, result), public_sandbox_result(result), generated schemas/examples.

- [x] Write unittest cases for the four-role enum, four input fields, request hash mismatch, independent stakeholder count, unknown speaker/source IDs, duplicate IDs, stale result identity, unsafe public raw-text disclosure, unavailable English translation, empty completed result and fixture mode.
- [x] Run the tests before implementation; retain the expected failure output.
- [x] Implement the Pydantic models, matching validation, public allowlist and async fixture adapter.
- [x] Run the tests and the fixture smoke. Export schemas and fixtures; check deterministic regeneration.
- [x] Review the verified task. Publication is recorded in the foundation PR.

Example behavior to test:

    request = make_example_request()
    result = await FixtureSandboxService().run(request)
    validate_sandbox_result(request, result)
    assert result.execution_mode == "fixture"
    assert "original_records" not in public_sandbox_result(result)
    altered = result.model_copy(update={"run_id": "another-run"})
    with self.assertRaises(ValueError):
        validate_sandbox_result(request, altered)

## Task 2: Ownership, handoffs and smoke command
Files: root AGENTS.md and README.md; backend/app/v2/AGENTS.md; backend/app/v2/sandbox/AGENTS.md; backend/tests/v2/sandbox/AGENTS.md; docs/v2/README.md; team/v2-core/{AGENTS,HANDOFF}.md; team/v2-sandbox/{AGENTS,HANDOFF}.md; scripts/check_v2_foundation.py.
Consumes: the Task 1 interface and fixtures.
Produces: two independent work packets and a single no-key verification command.

- [x] Document exact ownership and common branch ancestry.
- [x] Put setup, commands, interface fields, source-version handling, English output rules and acceptance criteria in the friend's handoff.
- [x] Put Metric naming and the remaining core work in Simon's handoff.
- [x] Add a root README link clearly identifying foundation-only status.
- [x] Add a smoke command that runs the fixture, validates provenance and public output, then verifies generated contracts.
- [x] Check documented setup/interface paths and executable foundation commands.

## Task 3: Verify and publish
Files: .github/workflows/v2-foundation.yml and foundation verification documentation.
Consumes: completed task outputs.
Produces: reviewed foundation commit, integration/core/Sandbox branches, verified links.

- [x] Run unittest discovery and smoke/schema checks without provider calls.
- [x] Independently review contracts, privacy of original text, status consistency, docs and branch workflow.
- [x] Fix concrete findings and rerun the affected checks.
- [ ] Commit changed files using the actual GitHub base tree and parent commit.
- [ ] Create the three new refs sequentially from the same verified foundation SHA.
- [ ] Verify all remote branch SHAs, handoff files, and unchanged main.

The final three external publication actions are recorded in the foundation PR
and delivery handoff after this source snapshot is committed.
