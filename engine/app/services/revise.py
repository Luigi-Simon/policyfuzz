"""Revision generation + recompilation of PolicyIR."""

from __future__ import annotations

from typing import Any

from app.contracts.policy import ChangeLogEntry, PolicyIR
from app.llm import LLMAdapter, LLMError
from app.services.compile import compile_ir
from app.services.extract import EXTRACT_SYSTEM, _ir_from_llm

REVISE_SYSTEM = (
    EXTRACT_SYSTEM
    + """

You are revising an existing PolicyIR.
Apply the user's instruction. Keep rule ids stable when the rule still exists
(R001, R002, ...). Add new ids at the end. Remove rules that the instruction
explicitly repeals. Put a short summary of what changed in "revision_summary".
Preserve citations; if you rewrite a rule, cite the original quote plus a note
in tags like "revised".
"""
)


class RevisionError(ValueError):
    """Safe failure to produce a validated, executable policy revision."""


def revise_policy_ir(
    ir: PolicyIR,
    instruction: str,
    llm: LLMAdapter | None = None,
) -> PolicyIR:
    if not instruction.strip():
        raise ValueError("Revision instruction is empty")

    adapter = llm or LLMAdapter()
    if not adapter.enabled:
        raise RevisionError(
            "Policy revision requires a configured model. The current policy was not changed."
        )
    try:
        raw = adapter.complete_json(
            system=REVISE_SYSTEM,
            user=_revise_user_prompt(ir, instruction),
        )
        revised = _ir_from_llm(ir.source, raw)
        if _executable_rules(revised) == _executable_rules(ir):
            raise RevisionError(
                "Policy revision did not change executable rules. The current policy was not changed."
            )
        return _stamp(
            ir, revised, instruction, raw.get("revision_summary") or instruction
        )
    except RevisionError:
        raise
    except (LLMError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise RevisionError(
            "Policy revision could not be validated. The current policy was not changed."
        ) from error


def _executable_rules(ir: PolicyIR) -> dict[str, Any]:
    return {
        rule.id: {
            **rule.model_dump(
                include={"applies_to", "when", "except_when", "parameters"}
            ),
            "then": [effect.model_dump(exclude={"details"}) for effect in rule.then],
        }
        for rule in ir.rules
    }


def _stamp(
    previous: PolicyIR, revised: PolicyIR, instruction: str, summary: str
) -> PolicyIR:
    revised.policy_id = previous.policy_id
    revised.parent_revision = previous.revision
    revised.revision = previous.revision + 1
    revised.change_log = [
        *previous.change_log,
        ChangeLogEntry(
            revision=revised.revision, instruction=instruction, summary=summary
        ),
    ]
    revised.source = previous.source
    return compile_ir(revised)


def _revise_user_prompt(ir: PolicyIR, instruction: str) -> str:
    slim: dict[str, Any] = ir.model_dump(exclude={"index", "source", "change_log"})
    slim["source_filename"] = ir.source.filename
    slim["source_excerpt"] = ir.source.text[:12000]
    return f"Current PolicyIR JSON:\n{slim}\n\nRevision instruction:\n{instruction}\n"
