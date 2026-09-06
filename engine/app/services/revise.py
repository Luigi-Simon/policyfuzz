"""Revision generation + recompilation of PolicyIR."""

from __future__ import annotations

from typing import Any

from app.contracts.policy import ChangeLogEntry, PolicyIR
from app.llm import LLMAdapter, LLMError
from app.services.compile import compile_ir
from app.services.extract import EXTRACT_SYSTEM, _ir_from_llm

REVISE_SYSTEM = EXTRACT_SYSTEM + """

You are revising an existing PolicyIR.
Apply the user's instruction. Keep rule ids stable when the rule still exists
(R001, R002, ...). Add new ids at the end. Remove rules that the instruction
explicitly repeals. Put a short summary of what changed in "revision_summary".
Preserve citations; if you rewrite a rule, cite the original quote plus a note
in tags like "revised".
"""


def revise_policy_ir(
    ir: PolicyIR,
    instruction: str,
    llm: LLMAdapter | None = None,
) -> PolicyIR:
    if not instruction.strip():
        raise ValueError("Revision instruction is empty")

    adapter = llm or LLMAdapter()
    if adapter.enabled:
        try:
            raw = adapter.complete_json(
                system=REVISE_SYSTEM,
                user=_revise_user_prompt(ir, instruction),
            )
            revised = _ir_from_llm(ir.source, raw)
            return _stamp(ir, revised, instruction, raw.get("revision_summary") or instruction)
        except (LLMError, ValueError, KeyError, TypeError):
            pass
    return compile_ir(_heuristic_revise(ir, instruction))


def _stamp(previous: PolicyIR, revised: PolicyIR, instruction: str, summary: str) -> PolicyIR:
    revised.policy_id = previous.policy_id
    revised.parent_revision = previous.revision
    revised.revision = previous.revision + 1
    revised.change_log = [
        *previous.change_log,
        ChangeLogEntry(revision=revised.revision, instruction=instruction, summary=summary),
    ]
    revised.source = previous.source
    return compile_ir(revised)


def _heuristic_revise(ir: PolicyIR, instruction: str) -> PolicyIR:
    clone = PolicyIR.model_validate(ir.model_dump())
    clone.parent_revision = ir.revision
    clone.revision = ir.revision + 1
    clone.open_questions = list(dict.fromkeys([*clone.open_questions, f"Pending revision: {instruction}"]))
    for rule in clone.rules:
        if "revised" not in rule.tags:
            rule.tags = [*rule.tags, "revised-pending-llm"]
        rule.ambiguity = (rule.ambiguity + " " if rule.ambiguity else "") + f"Revision requested: {instruction}"
    clone.change_log = [
        *ir.change_log,
        ChangeLogEntry(
            revision=clone.revision,
            instruction=instruction,
            summary="Recorded without LLM; re-run with LLM_API_KEY to rewrite rules.",
        ),
    ]
    return clone


def _revise_user_prompt(ir: PolicyIR, instruction: str) -> str:
    slim: dict[str, Any] = ir.model_dump(exclude={"index", "source", "change_log"})
    slim["source_filename"] = ir.source.filename
    slim["source_excerpt"] = ir.source.text[:12000]
    return (
        "Current PolicyIR JSON:\n"
        f"{slim}\n\n"
        "Revision instruction:\n"
        f"{instruction}\n"
    )
