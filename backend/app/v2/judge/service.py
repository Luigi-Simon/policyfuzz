"""Evidence-bound advisory Judge, implementing the shared async JudgeService."""

import asyncio
import json
import unicodedata
from copy import deepcopy

from app.v2.contracts import ExecutionMode
from app.v2.judge_contracts import (
    JudgeRequest,
    JudgeResult,
    judge_request_fingerprint,
    validate_judge_result,
)

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
            "mandatory_limitations": list(index.limitations),
            "repair_codes": [],
        }

        def failure(code: str, detail: str) -> JudgeResult:
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
        review_schema = strict_schema(GroundingReview.model_json_schema())
        try:
            async with asyncio.timeout(self._timeout):
                for _ in range(self._max_repairs + 1):
                    raw = await self._client.complete(
                        system_prompt=JUDGE_PROMPT,
                        payload=deepcopy(payload),
                        response_schema=deepcopy(schema),
                    )
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
                        if (
                            result.recommendation == "consider_limited_pilot"
                            and not index.pilot_eligible
                        ):
                            raise ValueError("Pilot gate is closed")
                    except (ValueError, TypeError, RecursionError):
                        payload["repair_codes"] = ["invalid_output"]
                        continue

                    review_payload = deepcopy(payload)
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
