"""HTTP client for the sidecar Policy Rehearsal engine.

Person 1's workflow/API owns the public ``/api/v1`` surface. This client is the
only supported way for PolicyFuzz backend code to call the engine sitting
behind that orchestration layer.

Environment:
  POLICY_ENGINE_BASE_URL  default http://127.0.0.1:8000
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol, Self

import httpx

from app.features.fuzzing.types import (
    EffectivenessView,
    RehearsalRequest,
    RehearsalResult,
    RevisionHintView,
)

DEFAULT_ENGINE_BASE_URL = "http://127.0.0.1:8001"


class EngineClientError(RuntimeError):
    """Engine call failed; ``code`` is stable for Person 1 error mapping."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(message or code)


class PolicyEngineClient(Protocol):
    """Stage protocol Person 1 can depend on without importing HTTP details."""

    def health(self) -> dict[str, Any]: ...

    def create_rehearsal(self, request: RehearsalRequest) -> RehearsalResult: ...

    def get_rehearsal(self, engine_run_id: str) -> RehearsalResult: ...

    def get_effectiveness(self, engine_run_id: str) -> EffectivenessView: ...

    def rehearse(self, engine_run_id: str, *, swarm: bool = True) -> RehearsalResult: ...

    def revise(self, engine_run_id: str, instruction: str) -> RehearsalResult: ...


class HttpPolicyEngineClient:
    """Calls the sidecar engine at ``/v1/...`` (not the public frontend API)."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        resolved = (
            base_url
            or os.environ.get("POLICY_ENGINE_BASE_URL")
            or DEFAULT_ENGINE_BASE_URL
        ).rstrip("/")
        self.base_url = resolved
        self._owns_client = client is None
        self._client = client or httpx.Client(base_url=resolved, timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def health(self) -> dict[str, Any]:
        response = self._client.get("/health")
        return self._parse(response, "ENGINE_HEALTH_FAILED")

    def create_rehearsal(self, request: RehearsalRequest) -> RehearsalResult:
        if not request.policy_text.strip():
            raise EngineClientError("ENGINE_EMPTY_POLICY", "policy_text is required")
        data: dict[str, Any] = {
            "policy_text": request.policy_text,
            "seed_text": request.seed_text,
            "population_size": str(max(1, min(int(request.population_size), 50))),
        }
        if request.locale:
            data["locale"] = request.locale
        if request.groups:
            data["groups"] = ",".join(request.groups)
        if request.segments:
            data["audience_json"] = json.dumps(
                [item.to_payload() for item in request.segments]
            )
        response = self._client.post("/v1/runs", data=data)
        payload = self._parse(response, "ENGINE_CREATE_FAILED")
        return _to_result(payload)

    def get_rehearsal(self, engine_run_id: str) -> RehearsalResult:
        response = self._client.get(f"/v1/runs/{engine_run_id}")
        payload = self._parse(response, "ENGINE_GET_FAILED")
        return _to_result(payload)

    def get_effectiveness(self, engine_run_id: str) -> EffectivenessView:
        response = self._client.get(f"/v1/runs/{engine_run_id}/effectiveness")
        payload = self._parse(response, "ENGINE_EFFECTIVENESS_FAILED")
        return _to_effectiveness(payload)

    def rehearse(self, engine_run_id: str, *, swarm: bool = True) -> RehearsalResult:
        response = self._client.post(
            f"/v1/runs/{engine_run_id}/rehearse",
            params={"swarm": str(swarm).lower()},
        )
        return _to_result(self._parse(response, "ENGINE_REHEARSE_FAILED"))

    def revise(self, engine_run_id: str, instruction: str) -> RehearsalResult:
        if not instruction.strip():
            raise EngineClientError(
                "ENGINE_EMPTY_INSTRUCTION", "instruction is required"
            )
        response = self._client.post(
            f"/v1/runs/{engine_run_id}/revise",
            json={"instruction": instruction.strip()},
        )
        payload = self._parse(response, "ENGINE_REVISE_FAILED")
        return _to_result(payload)

    def _parse(self, response: httpx.Response, code: str) -> dict[str, Any]:
        try:
            payload = response.json() if response.content else {}
        except ValueError as error:
            raise EngineClientError(
                code, f"non-JSON response HTTP {response.status_code}"
            ) from error
        if response.status_code >= 400:
            detail = payload.get("detail") if isinstance(payload, dict) else payload
            raise EngineClientError(code, f"HTTP {response.status_code}: {detail}")
        if not isinstance(payload, dict):
            raise EngineClientError(code, "expected JSON object")
        return payload


def _to_result(payload: dict[str, Any]) -> RehearsalResult:
    ir = payload.get("ir") if isinstance(payload.get("ir"), dict) else {}
    suite = payload.get("suite") if isinstance(payload.get("suite"), dict) else {}
    effectiveness_raw = payload.get("effectiveness")
    effectiveness = (
        _to_effectiveness(effectiveness_raw)
        if isinstance(effectiveness_raw, dict)
        else None
    )
    scenarios = suite.get("scenarios") if isinstance(suite, dict) else None
    return RehearsalResult(
        engine_run_id=str(payload.get("run_id") or ""),
        status=str(payload.get("status") or ""),
        policy_id=(ir or {}).get("policy_id"),
        policy_revision=(ir or {}).get("revision"),
        rule_count=len((ir or {}).get("rules") or []),
        scenario_count=len(scenarios or []),
        score=effectiveness.score if effectiveness else None,
        effectiveness=effectiveness,
        error=payload.get("error"),
        raw=payload,
    )


def _to_effectiveness(payload: dict[str, Any]) -> EffectivenessView:
    hints: list[RevisionHintView] = []
    for item in payload.get("recommended_actions") or []:
        if not isinstance(item, dict):
            continue
        hints.append(
            RevisionHintView(
                rule_ids=tuple(str(rid) for rid in (item.get("rule_ids") or [])),
                action=str(item.get("action") or "clarify"),
                summary=str(item.get("summary") or ""),
            )
        )
    return EffectivenessView(
        score=int(payload.get("score") or 0),
        justification=str(payload.get("justification") or ""),
        recommended_actions=tuple(hints),
        swarm_used=bool(payload.get("swarm_used")),
        metrics=dict(payload.get("metrics") or {}),
    )
