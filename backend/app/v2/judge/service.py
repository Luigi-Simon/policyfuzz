"""Evidence-bound advisory Judge, implementing the shared async JudgeService."""

import asyncio
import json
import re
import unicodedata
from copy import deepcopy

from app.v2.contracts import ExecutionMode
from app.v2.diagnostics import record
from app.v2.judge_contracts import (
    JudgeRequest,
    JudgeResult,
    NextStep,
    judge_request_fingerprint,
    validate_judge_result,
)

from .citations import check_citations, repair_citations
from .client import JudgeModelClient, validate_timeout
from .evidence import index_evidence, label_mock_provenance, validate_interactions
from .prompts import EDITORIAL_FIELDS, JUDGE_PROMPT, REVIEW_PROMPT
from .schema import GroundingReview, editorial_schema, strict_schema


def _json_object(raw: str) -> dict:
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > 131072:
        raise ValueError("Invalid response size")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def invalid_number(value):
        raise ValueError("Non-finite JSON number")

    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_number)
    if not isinstance(value, dict):
        raise TypeError("Response must be an object")
    return value


def _check_prose(result: JudgeResult) -> None:
    if any(
        re.search(
            r"\b(?:revise|rewrite|correct|edit|repair|update)\s+(?:the\s+)?(?:finding|draft|report)\b",
            step.action,
            re.IGNORECASE,
        )
        for step in result.next_steps
    ):
        raise ValueError("Repair instructions are not user-facing policy advice")
    texts = [result.summary, *result.limitations]
    texts.extend(
        item.text for item in (*result.pros, *result.cons, *result.key_interactions)
    )
    texts.extend(
        text for step in result.next_steps for text in (step.action, step.reason)
    )
    # A conservative script check supplements (not replaces) the semantic
    # review, which also checks non-English prose written in Latin characters.
    for text in texts:
        if any(c.isalpha() and "LATIN" not in unicodedata.name(c, "") for c in text):
            raise ValueError("Non-English script in generated prose")


class JudgeAgentService:
    def __init__(
        self,
        client: JudgeModelClient,
        *,
        timeout_seconds: float = 90,
        max_repairs: int = 1,
        max_input_bytes: int = 524288,
    ):
        self._mode = ExecutionMode(client.execution_mode)
        self._client = client
        self._timeout = validate_timeout(timeout_seconds)
        if type(max_repairs) is not int or not 0 <= max_repairs <= 2:
            raise ValueError("Judge allows zero to two repairs")
        if type(max_input_bytes) is not int or not 1024 <= max_input_bytes <= 2097152:
            raise ValueError("Invalid Judge input size limit")
        self._max_repairs = max_repairs
        self._max_input_bytes = max_input_bytes

    async def run(self, request: JudgeRequest) -> JudgeResult:
        # Snapshot and fully revalidate: frozen models can still be constructed
        # or copied without validation, and callers must retain their evidence.
        request = JudgeRequest.model_validate_json(request.model_dump_json())
        index = index_evidence(request, self._mode.value)
        identity = {
            "request_id": request.request_id,
            "run_id": request.run_id,
            "policy_version": request.policy_version,
            "policy_text_sha256": request.policy_text_sha256,
            "request_fingerprint": judge_request_fingerprint(request),
            "execution_mode": self._mode,
        }
        # No original policy is supplied here. Without a reviewed interpretation,
        # an LLM cannot establish that a provision is absent. Enforce this before
        # generation instead of relying on a second model to catch the inference.
        qualitative_only = (
            request.metric is None
            or request.metric.review.status != "ready"
            or request.metric.generation_method == "policy_conditions"
        )
        comparison_only = bool(
            request.metric and request.metric.generation_method == "policy_conditions"
        )
        comparison_summary = (
            f"Metric local comparison results: {request.metric.passed} passed, {request.metric.failed} failed, {request.metric.unscored} unscored. These checks exercise an interpreted model, not an independent policy implementation. Stakeholder observations and proposed checks are qualitative; no policy strengths, defects or pilot recommendation are established."
            if comparison_only
            else None
        )
        has_discussion = any(ref.kind == "sandbox_message" for ref in index.citations)
        if qualitative_only and not has_discussion:
            result = JudgeResult(
                **identity,
                status="partial",
                recommendation="insufficient_evidence",
                summary=comparison_summary
                + " No usable stakeholder discussion was supplied; inspect the Sandbox stage before retrying."
                if comparison_only
                else "A policy recommendation is unavailable: no supported executable interpretation or usable stakeholder discussion was supplied. Inspect the Sandbox stage failure or missing evidence before retrying.",
                next_steps=(
                    NextStep(
                        action="Inspect Sandbox errors and restore participant setup or evidence capture before rerunning the workflow.",
                        reason="No usable stakeholder messages reached Judge, so no interaction or sentiment conclusion is available.",
                    ),
                    NextStep(
                        action="Review the submitted policy's actual provisions and define supported, testable requirements before requesting a policy recommendation.",
                        reason="The current Metric engine's input limitation does not establish a missing provision or a policy defect.",
                    ),
                ),
                limitations=tuple(
                    dict.fromkeys(
                        (
                            *request.limitations,
                            *index.limitations,
                            "The Judge model was not called: no usable stakeholder messages were available, and local comparison evidence alone cannot support policy advice."
                            if comparison_only
                            else "The Judge model was not called: neither an executable interpretation nor usable stakeholder messages were available. No policy findings were inferred.",
                        )
                    )
                ),
            )
            validate_judge_result(request, result)
            return result
        payload = {
            "request": request.model_dump(mode="json"),
            "judge_execution_mode": self._mode.value,
            "available_citations": [
                ref.model_dump(mode="json") for ref in index.citations
            ],
            "verified_reply_pairs": [
                {"parent_message_id": p, "reply_message_id": r}
                for p, r in index.reply_pairs
            ],
            "pilot_recommendation_allowed": index.pilot_eligible,
            "qualitative_only": qualitative_only,
            "mandatory_limitations": list(index.limitations),
            "repair_codes": [],
        }

        def failure(code: str, detail: str) -> JudgeResult:
            record("judge", "failed", code=code)
            result = JudgeResult(
                **identity,
                status="failed",
                recommendation="insufficient_evidence",
                summary="Judge advice is unavailable. No policy recommendation was produced.",
                limitations=index.limitations,
                errors=(f"{code}: {detail}",),
            )
            validate_judge_result(request, result)
            return result

        if (
            len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            > self._max_input_bytes
        ):
            return failure(
                "judge_input_too_large",
                "The supplied evidence exceeds the configured Judge input limit; no evidence was silently truncated.",
            )

        schema = editorial_schema(index)
        if qualitative_only:
            schema["properties"]["recommendation"]["enum"] = ["insufficient_evidence"]
            for key in ("pros", "cons"):
                schema["properties"][key]["maxItems"] = 0
        review_schema = strict_schema(GroundingReview.model_json_schema())
        citation_cache = {}
        pending_draft = None
        try:
            async with asyncio.timeout(self._timeout):
                for attempt in range(self._max_repairs + 1):
                    record("judge_generation", "started", attempt=attempt + 1)
                    if pending_draft is None:
                        raw = await self._client.complete(
                            system_prompt=JUDGE_PROMPT,
                            payload=deepcopy(payload),
                            response_schema=deepcopy(schema),
                        )
                    else:
                        raw = json.dumps(pending_draft)
                        pending_draft = None
                    try:
                        draft = _json_object(raw)
                        if set(draft) != set(EDITORIAL_FIELDS):
                            raise ValueError("Unexpected or missing editorial fields")
                        result = JudgeResult.model_validate(
                            {
                                **draft,
                                **identity,
                                "status": "partial"
                                if index.incomplete
                                else "completed",
                            }
                        )
                        if comparison_only:
                            result = result.model_copy(
                                update={"summary": comparison_summary}
                            )
                        result = label_mock_provenance(request, result)
                        _check_prose(result)
                        result = result.model_copy(
                            update={
                                "limitations": tuple(
                                    dict.fromkeys(
                                        (*result.limitations, *index.limitations)
                                    )
                                )
                            }
                        )
                        validate_judge_result(request, result)
                        validate_interactions(result, index)
                        if qualitative_only and (
                            result.pros
                            or result.cons
                            or result.recommendation != "insufficient_evidence"
                        ):
                            raise ValueError(
                                "Qualitative review cannot assign policy findings or a revision verdict"
                            )
                        if (
                            result.recommendation == "consider_limited_pilot"
                            and not index.pilot_eligible
                        ):
                            raise ValueError("Pilot gate is closed")
                    except (ValueError, TypeError, RecursionError):
                        payload["repair_codes"] = ["invalid_output"]
                        continue

                    review_payload = deepcopy(payload)
                    record("judge_review", "started", attempt=attempt + 1)
                    review_payload["draft"] = result.model_dump(
                        mode="json", include=set(EDITORIAL_FIELDS)
                    )
                    raw_review = await self._client.complete(
                        system_prompt=REVIEW_PROMPT,
                        payload=review_payload,
                        response_schema=deepcopy(review_schema),
                    )
                    try:
                        review = GroundingReview.model_validate(
                            _json_object(raw_review)
                        )
                    except (ValueError, TypeError, RecursionError):
                        payload["repair_codes"] = ["grounding_review_invalid"]
                        continue
                    if (
                        review.issues
                        or review.feedback
                        or not all(
                            value
                            for key, value in review.model_dump().items()
                            if key not in ("issues", "feedback")
                        )
                    ):
                        payload["repair_codes"] = list(
                            dict.fromkeys(review.issues)
                        ) or ["unsupported_claim"]
                        payload["previous_draft"] = review_payload["draft"]
                        payload["repair_feedback"] = [
                            item.model_dump(mode="json") for item in review.feedback
                        ]
                        continue
                    record("judge_citations", "started", attempt=attempt + 1)
                    feedback = await check_citations(
                        self._client, request, result, _json_object, citation_cache
                    )
                    if feedback:
                        record(
                            "judge_citations",
                            "failed",
                            attempt=attempt + 1,
                            code="citation_not_supported",
                        )
                        payload["repair_codes"] = ["citation_not_supported"]
                        payload["previous_draft"] = review_payload["draft"]
                        payload["repair_feedback"] = feedback
                        if attempt < self._max_repairs:
                            record(
                                "judge_citation_repair",
                                "started",
                                attempt=attempt + 1,
                                count=len(feedback),
                            )
                            pending_draft = await repair_citations(
                                self._client, request, result, feedback, _json_object
                            )
                        else:
                            # Keep only independently accepted cited items. The
                            # failed draft's summary/recommendation cannot survive
                            # removal of their possible supporting findings.
                            rejected = {(f["field"], f["item_index"]) for f in feedback}
                            data = result.model_dump(mode="json")
                            for field in (
                                "pros",
                                "cons",
                                "next_steps",
                                "key_interactions",
                            ):
                                data[field] = [
                                    item
                                    for i, item in enumerate(data[field])
                                    if (field, i) not in rejected
                                ]
                            data.update(
                                status="partial",
                                recommendation="insufficient_evidence",
                                summary="Judge retained only findings that passed validation against their own cited evidence. Some generated findings could not be validated and were omitted; a policy recommendation is withheld.",
                            )
                            data["limitations"].append(
                                f"Citation validation: {len(rejected)} generated finding(s) were omitted after the bounded validation attempts. Retained findings passed their individual citation checks; omitted text is not evidence."
                            )
                            if not data["next_steps"]:
                                data["next_steps"] = [
                                    NextStep(
                                        action="Review the original policy and collect independently checked requirements and implementation evidence before requesting a recommendation.",
                                        reason="Additional verified evidence is needed for a policy recommendation.",
                                    ).model_dump(mode="json")
                                ]
                            limited = JudgeResult.model_validate(data)
                            validate_judge_result(request, limited)
                            validate_interactions(limited, index)
                            record(
                                "judge_citations",
                                "partial",
                                count=len(rejected),
                                code="unsupported_findings_omitted",
                            )
                            return limited
                        continue
                    record("judge_citations", "completed", attempt=attempt + 1)
                    return result
        except TimeoutError:
            return failure(
                "judge_timeout",
                "The Judge deadline expired before advice could be validated.",
            )
        except Exception:  # noqa: BLE001 - sanitize failures from injected providers
            # No exception messages, raw output, credential strings or provider
            # bodies cross the public boundary. CancelledError propagates.
            return failure(
                "judge_provider_error",
                "The configured Judge provider did not complete successfully.",
            )
        return failure(
            "judge_invalid_output",
            "Judge output failed validation after the configured repair attempts. "
            + "Validation codes: "
            + ", ".join(payload["repair_codes"])
            + ".",
        )
