"""Provider schemas derived from shared result types; no parallel Judge models."""

from copy import deepcopy
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.v2.judge_contracts import JudgeResult

from .prompts import EDITORIAL_FIELDS


class ReviewFeedback(BaseModel):
    """Brief evidence mismatch, not hidden deliberation or public advice."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    field: Literal[
        "summary",
        "recommendation",
        "pros",
        "cons",
        "next_steps",
        "key_interactions",
        "limitations",
    ]
    item_index: int | None = Field(ge=0, le=19)
    problem: str = Field(min_length=1, max_length=400)


class GroundingReview(BaseModel):
    """Private validation-tool output, never part of the public Judge contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    english: bool = Field(strict=True)
    claims_grounded: bool = Field(strict=True)
    metric_results_preserved: bool = Field(strict=True)
    interaction_claims_grounded: bool = Field(strict=True)
    limitations_preserved: bool = Field(strict=True)
    provenance_preserved: bool = Field(strict=True)
    issues: list[
        Literal[
            "non_english",
            "unsupported_claim",
            "metric_contradiction",
            "unsupported_interaction",
            "missing_limitation",
            "fixture_misrepresented",
        ]
    ] = Field(max_length=20)
    feedback: list[ReviewFeedback] = Field(default_factory=list, max_length=20)


def strict_schema(source):
    schema = deepcopy(source)

    def visit(node):
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for item in node.values():
                visit(item)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(schema)
    # Remove unreferenced shared definitions (identity/status enums, etc.).
    definitions = schema.get("$defs", {})
    needed = set()

    def references(node):
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].rsplit("/", 1)[-1]
                if name not in needed and name in definitions:
                    needed.add(name)
                    references(definitions[name])
            for key, item in node.items():
                if key != "$defs":
                    references(item)
        elif isinstance(node, list):
            for item in node:
                references(item)

    references(schema)
    if "$defs" in schema:
        schema["$defs"] = {
            key: value for key, value in definitions.items() if key in needed
        }
    return schema


def editorial_schema(index):
    schema = JudgeResult.model_json_schema()
    schema["properties"] = {key: schema["properties"][key] for key in EDITORIAL_FIELDS}
    if not index.pilot_eligible:
        schema["properties"]["recommendation"]["enum"] = [
            "revise_before_pilot",
            "insufficient_evidence",
        ]
    if not index.reply_pairs:
        schema["properties"]["key_interactions"]["maxItems"] = 0
    groups = {}
    for ref in index.citations:
        groups.setdefault((ref.kind, ref.case_id), []).append(ref.id)
    branches = []
    for (kind, case_id), ids in groups.items():
        branches.append(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {"type": "string", "enum": [kind]},
                    "id": {"type": "string", "enum": ids},
                    "case_id": {"type": "string", "enum": [case_id]}
                    if case_id is not None
                    else {"type": "null"},
                },
                "required": ["kind", "id", "case_id"],
            }
        )
    if branches:
        schema["$defs"]["Citation"] = {"anyOf": branches}
    else:
        for key in ("pros", "cons", "key_interactions"):
            schema["properties"][key]["maxItems"] = 0
        schema["$defs"]["NextStep"]["properties"]["citations"]["maxItems"] = 0
    return strict_schema(schema)
