"""Scenario synthesis, validation, planning, and sidecar engine client.

Person 1 owns the public ``/api/v1`` API. Call into this package from workflow
to reach the rehearsal engine behind that orchestration layer.
"""

from app.features.fuzzing.engine_client import (
    EngineClientError,
    HttpPolicyEngineClient,
    PolicyEngineClient,
)
from app.features.fuzzing.types import (
    AudienceSegmentInput,
    EffectivenessView,
    RehearsalRequest,
    RehearsalResult,
    RevisionHintView,
)

__all__ = [
    "AudienceSegmentInput",
    "EffectivenessView",
    "EngineClientError",
    "HttpPolicyEngineClient",
    "PolicyEngineClient",
    "RehearsalRequest",
    "RehearsalResult",
    "RevisionHintView",
]
