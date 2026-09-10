# Sandbox contributor ownership

This directory belongs to Simon's MiroFish/Sandbox contributor.
Read team/v2-sandbox/HANDOFF.md before implementation.

Implement the Sandbox Agent behind app.v2.protocols.SandboxService.
Shared models in app.v2.contracts are owned by Simon.
Own MiroFish integration, personas, capture, parsing and English output.
Return simulation observations, not formal policy verdicts or the Judge Agent's final recommendations.
Do not create additional top-level agent roles.

Keep changes here and in backend/tests/v2/sandbox/**. Propose dependency or configuration edits to Simon.
Existing engine/app/services/mirofish_bridge.py and mirofish_runner.py are reference implementations; port reusable logic without silently changing the legacy engine.

Do not put expected test outcomes into persona seeds.
Preserve request/run/policy identity and original evidence internally.
Return only validated English display fields publicly; failures use an English partial/error status.
Fixtures and tests cannot call a real provider.

