"""Cited rule extraction: PolicyDocument → PolicyIR."""

from __future__ import annotations

import re
from typing import Any

from app.contracts.common import Citation, new_id
from app.contracts.policy import (
    ActionSpec,
    ActorType,
    AttributeSchema,
    Obligation,
    PolicyDocument,
    PolicyIR,
    Predicate,
    Rule,
)
from app.llm import LLMAdapter, LLMError
from app.services.compile import compile_ir

EXTRACT_SYSTEM = """\
You compile written policy into a machine-checkable PolicyIR.

Return a single JSON object with this shape:
{
  "title": string,
  "jurisdiction": string | null,
  "actor_types": [
    {
      "id": "snake_case id",
      "label": "Human label",
      "description": string,
      "attributes": [
        {
          "name": "role|grade|age|...",
          "value_type": "string|integer|number|boolean|enum|datetime",
          "enum_values": ["..."] | null,
          "minimum": number | null,
          "maximum": number | null,
          "description": string
        }
      ]
    }
  ],
  "actions": [
    {"name": "snake_case", "description": string, "attributes": []}
  ],
  "rules": [
    {
      "title": string,
      "statement": "verbatim or near-verbatim rule text",
      "citations": [{"page": int | null, "section": string | null, "quote": "verbatim snippet"}],
      "applies_to": ["actor_type id"],
      "when": [{"field": "actor.role", "op": "eq", "value": "..."}],
      "then": [{"modality": "must|must_not|may|should", "action": "action name", "assignee": "actor", "details": string}],
      "except_when": [],
      "parameters": {"max_warnings": 2},
      "severity": "critical|high|medium|low",
      "tags": ["phones"],
      "ambiguity": string | null
    }
  ],
  "glossary": {"term": "definition"},
  "open_questions": ["unclear edge the fuzzer should target"],
  "conflicts": ["rule A vs rule B ..."]
}

Rules:
- Every rule MUST have at least one citation.quote copied from the source.
- Predicate fields MUST start with actor. or action. or context.
- applies_to values MUST be actor_types.id values you defined.
- then.action MUST match an actions.name you defined.
- Extract numeric thresholds (warnings, hours, ages, fines) into parameters.
- Prefer 8–40 rules over dumping every sentence.
- Surface genuine ambiguities in open_questions and rule.ambiguity.
"""


def extract_policy_ir(document: PolicyDocument, llm: LLMAdapter | None = None) -> PolicyIR:
    adapter = llm or LLMAdapter()
    if adapter.enabled:
        try:
            raw = adapter.complete_json(
                system=EXTRACT_SYSTEM,
                user=_user_prompt(document),
            )
            ir = _ir_from_llm(document, raw)
            return compile_ir(ir)
        except (LLMError, ValueError, KeyError, TypeError):
            # Fall through to heuristic so a bad model response still yields IR.
            pass
    return compile_ir(heuristic_extract(document))


def heuristic_extract(document: PolicyDocument) -> PolicyIR:
    """Deterministic fallback used in CI and when no LLM key is set."""
    sentences = _sentences(document)
    actor_types = _default_actors(sentences)
    actions = [
        ActionSpec(name="comply", description="Follow the stated requirement"),
        ActionSpec(name="use_device", description="Use a phone or other device"),
        ActionSpec(name="enforce", description="Authority enforces the rule"),
        ActionSpec(name="exempt", description="Claim or grant an exemption"),
        ActionSpec(name="appeal", description="Challenge a decision"),
    ]
    action_for_modality = {
        "must": "comply",
        "must_not": "use_device",
        "shall": "comply",
        "shall_not": "use_device",
        "may": "exempt",
        "should": "comply",
        "should_not": "use_device",
    }

    rules: list[Rule] = []
    for index, (page, sentence) in enumerate(sentences, start=1):
        modality = _modality(sentence)
        if not modality:
            continue
        applies = _guess_actors(sentence, actor_types)
        obligation_modality = {
            "shall": "must",
            "shall_not": "must_not",
            "should_not": "must_not",
        }.get(modality, modality)
        action_name = action_for_modality.get(modality, "comply")
        parameters = _extract_parameters(sentence)
        rules.append(
            Rule(
                id=f"R{index:03d}",
                title=_title(sentence),
                statement=sentence,
                citations=[
                    Citation(
                        document_id=document.document_id,
                        page=page,
                        quote=sentence[:280],
                    )
                ],
                applies_to=applies,
                when=[Predicate(field="actor.role", op="in", value=applies)] if applies else [],
                then=[
                    Obligation(
                        modality=obligation_modality,  # type: ignore[arg-type]
                        action=action_name,
                        assignee="actor",
                        details=sentence,
                    )
                ],
                except_when=_exceptions(sentence),
                parameters=parameters,
                severity="high" if obligation_modality in {"must", "must_not"} else "medium",
                tags=_tags(sentence),
                ambiguity=_ambiguity(sentence),
            )
        )

    if not rules:
        rules.append(
            Rule(
                id="R001",
                title="Unstructured policy text",
                statement=document.text[:500] or "No extractable normative sentences.",
                citations=[
                    Citation(
                        document_id=document.document_id,
                        page=1 if document.pages else None,
                        quote=(document.pages[0][:280] if document.pages else document.text[:280]),
                    )
                ],
                applies_to=[actor_types[0].id],
                when=[],
                then=[Obligation(modality="should", action="comply", details="Review source")],
                tags=["unstructured"],
                ambiguity="Source did not contain must/shall/may/should language.",
            )
        )

    title = _guess_title(document)
    return PolicyIR(
        title=title,
        source=document,
        actor_types=actor_types,
        actions=actions,
        rules=rules,
        open_questions=[
            rule.ambiguity for rule in rules if rule.ambiguity
        ],
    )


def _user_prompt(document: PolicyDocument) -> str:
    pages = []
    for index, page_text in enumerate(document.pages or [document.text], start=1):
        clipped = page_text[:6000]
        pages.append(f"--- page {index} ---\n{clipped}")
    body = "\n\n".join(pages)[:24000]
    return (
        f"Filename: {document.filename}\n"
        f"Pages: {document.page_count}\n\n"
        f"{body}"
    )


def _ir_from_llm(document: PolicyDocument, raw: dict[str, Any]) -> PolicyIR:
    actor_types = []
    for item in raw.get("actor_types") or []:
        attributes = [
            AttributeSchema(**attr) if isinstance(attr, dict) else attr
            for attr in item.get("attributes") or []
        ]
        actor_types.append(
            ActorType(
                id=item.get("id") or new_id("actor"),
                label=item.get("label") or item.get("id") or "Actor",
                description=item.get("description") or "",
                attributes=attributes,
            )
        )
    if not actor_types:
        actor_types = _default_actors([])

    actor_ids = {actor.id for actor in actor_types}
    actions = [
        ActionSpec(
            name=item.get("name") or "comply",
            description=item.get("description") or "",
            attributes=[
                AttributeSchema(**attr) if isinstance(attr, dict) else attr
                for attr in item.get("attributes") or []
            ],
        )
        for item in raw.get("actions") or []
    ]
    if not actions:
        actions = [ActionSpec(name="comply")]
    action_names = {action.name for action in actions}

    rules: list[Rule] = []
    for index, item in enumerate(raw.get("rules") or [], start=1):
        citations = []
        for cite in item.get("citations") or []:
            quote = (cite.get("quote") or item.get("statement") or "")[:280]
            citations.append(
                Citation(
                    document_id=document.document_id,
                    page=cite.get("page"),
                    section=cite.get("section"),
                    quote=quote,
                )
            )
        if not citations:
            citations.append(
                Citation(
                    document_id=document.document_id,
                    page=1 if document.pages else None,
                    quote=(item.get("statement") or "")[:280],
                )
            )
        applies = [aid for aid in (item.get("applies_to") or []) if aid in actor_ids]
        if not applies:
            applies = [actor_types[0].id]
        then = []
        for obl in item.get("then") or []:
            action_name = obl.get("action") or "comply"
            if action_name not in action_names:
                actions.append(ActionSpec(name=action_name))
                action_names.add(action_name)
            then.append(
                Obligation(
                    modality=obl.get("modality") or "must",
                    action=action_name,
                    assignee=obl.get("assignee") or "actor",
                    details=obl.get("details") or "",
                )
            )
        if not then:
            then = [Obligation(modality="must", action="comply")]
        rules.append(
            Rule(
                id=f"R{index:03d}",
                title=item.get("title") or _title(item.get("statement") or f"Rule {index}"),
                statement=item.get("statement") or item.get("title") or "",
                citations=citations,
                applies_to=applies,
                when=[_safe_predicate(pred) for pred in item.get("when") or [] if isinstance(pred, dict)],
                then=then,
                except_when=[
                    _safe_predicate(pred)
                    for pred in item.get("except_when") or []
                    if isinstance(pred, dict)
                ],
                parameters=item.get("parameters") or {},
                severity=item.get("severity") or "medium",
                tags=item.get("tags") or [],
                ambiguity=item.get("ambiguity"),
            )
        )

    return PolicyIR(
        title=raw.get("title") or _guess_title(document),
        jurisdiction=raw.get("jurisdiction"),
        source=document,
        actor_types=actor_types,
        actions=actions,
        rules=rules,
        glossary=raw.get("glossary") or {},
        open_questions=raw.get("open_questions") or [],
        conflicts=raw.get("conflicts") or [],
    )


def _safe_predicate(raw: dict[str, Any]) -> Predicate:
    try:
        return Predicate(**raw)
    except (TypeError, ValueError):
        return Predicate(field="context.unparsed", op="eq", value=raw)


def _sentences(document: PolicyDocument) -> list[tuple[int | None, str]]:
    found: list[tuple[int | None, str]] = []
    pages = document.pages or ([document.text] if document.text else [])
    for index, page in enumerate(pages, start=1):
        chunks = re.split(r"(?<=[.!?])\s+", page.replace("\n", " "))
        for chunk in chunks:
            sentence = re.sub(r"\s+", " ", chunk).strip()
            if len(sentence) < 20:
                continue
            found.append((index, sentence))
    return found


def _modality(sentence: str) -> str | None:
    lower = sentence.lower()
    patterns = [
        ("must not", "must_not"),
        ("shall not", "shall_not"),
        ("should not", "should_not"),
        ("must", "must"),
        ("shall", "shall"),
        ("may not", "must_not"),
        ("may", "may"),
        ("should", "should"),
        ("is required to", "must"),
        ("is prohibited", "must_not"),
        ("is forbidden", "must_not"),
    ]
    for needle, value in patterns:
        if needle in lower:
            return value
    return None


def _default_actors(sentences: list[tuple[int | None, str]]) -> list[ActorType]:
    corpus = " ".join(text for _, text in sentences).lower()
    catalog = [
        ("student", "Student", ["student", "pupil", "learner"]),
        ("teacher", "Teacher", ["teacher", "faculty", "instructor"]),
        ("parent", "Parent / guardian", ["parent", "guardian"]),
        ("administrator", "Administrator", ["principal", "administrator", "headteacher", "director"]),
        ("employee", "Employee", ["employee", "staff", "worker"]),
        ("public", "Member of the public", ["resident", "citizen", "public", "visitor"]),
    ]
    chosen: list[ActorType] = []
    for actor_id, label, needles in catalog:
        if any(needle in corpus for needle in needles):
            chosen.append(_actor(actor_id, label))
    if not chosen:
        chosen = [_actor("subject", "Policy subject")]
    return chosen


def _actor(actor_id: str, label: str) -> ActorType:
    return ActorType(
        id=actor_id,
        label=label,
        attributes=[
            AttributeSchema(name="role", value_type="enum", enum_values=[actor_id], description="Actor role"),
            AttributeSchema(name="age", value_type="integer", minimum=0, maximum=120),
            AttributeSchema(name="location", value_type="string", description="Where the action happens"),
        ],
    )


def _guess_actors(sentence: str, actor_types: list[ActorType]) -> list[str]:
    lower = sentence.lower()
    matched = [actor.id for actor in actor_types if actor.id in lower or actor.label.lower() in lower]
    return matched or [actor.id for actor in actor_types]


def _exceptions(sentence: str) -> list[Predicate]:
    lower = sentence.lower()
    if "except" in lower or "unless" in lower or "exempt" in lower:
        return [Predicate(field="context.exemption", op="eq", value=True)]
    return []


def _extract_parameters(sentence: str) -> dict[str, Any]:
    params: dict[str, Any] = {}
    numbers = re.findall(r"\b(\d+)\b", sentence)
    if numbers:
        params["mentioned_numbers"] = [int(item) for item in numbers[:5]]
    times = re.findall(r"\b(\d{1,2}:\d{2})\b", sentence)
    if times:
        params["times"] = times
    return params


def _tags(sentence: str) -> list[str]:
    tags = []
    lower = sentence.lower()
    for tag in ("phone", "device", "safety", "privacy", "attendance", "fee", "uniform", "data"):
        if tag in lower:
            tags.append(tag)
    return tags


def _ambiguity(sentence: str) -> str | None:
    lower = sentence.lower()
    if any(word in lower for word in ("reasonable", "appropriate", "as needed", "may", "where practicable")):
        return "Discretionary language — good adversarial / targeted target."
    return None


def _title(sentence: str) -> str:
    trimmed = sentence.strip()
    if len(trimmed) <= 72:
        return trimmed.rstrip(".")
    return trimmed[:69].rstrip() + "…"


def _guess_title(document: PolicyDocument) -> str:
    first = (document.pages[0] if document.pages else document.text).strip().splitlines()
    for line in first:
        candidate = line.strip()
        if 8 <= len(candidate) <= 120:
            return candidate
    return document.filename
