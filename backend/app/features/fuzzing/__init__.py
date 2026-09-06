"""Scenario synthesis, validation, planning, and sidecar engine client.

Person 1 owns the public ``/api/v1`` API. Call into this package from workflow
to reach the rehearsal engine behind that orchestration layer.
"""

from app.features.fuzzing.engine_client import (
    EngineClientError,
    HttpPolicyEngineClient,
    PolicyEngineClient,
)
from app.features.fuzzing.exploratory import (
    ExploratoryBatchPayload,
    ExploratoryScenarioPayload,
    ModelOutputValidationError,
    PromptCommitmentError,
    exploratory_response_example,
)
from app.features.fuzzing.planner import (
    CoverageLimitExceededError,
    DefaultScenarioPlanner,
)
from app.features.fuzzing.prompts import exploratory_prompt_commitment
from app.features.fuzzing.types import (
    AudienceSegmentInput,
    EffectivenessView,
    RehearsalRequest,
    RehearsalResult,
    RevisionHintView,
)

__all__ = [
    "AudienceSegmentInput",
    "CoverageLimitExceededError",
    "DefaultScenarioPlanner",
    "EffectivenessView",
    "EngineClientError",
    "ExploratoryBatchPayload",
    "ExploratoryScenarioPayload",
    "HttpPolicyEngineClient",
    "ModelOutputValidationError",
    "PolicyEngineClient",
    "PromptCommitmentError",
    "RehearsalRequest",
    "RehearsalResult",
    "RevisionHintView",
    "exploratory_prompt_commitment",
    "exploratory_response_example",
]
