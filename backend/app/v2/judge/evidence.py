"""Judge-local evidence indexing and conservative recommendation gates."""

from dataclasses import dataclass

from app.v2.judge_contracts import Citation, JudgeRequest, JudgeResult


def unique(values):
    if len(values) != len(set(values)):
        raise ValueError("Ambiguous evidence identifiers")


@dataclass(frozen=True)
class EvidenceIndex:
    citations: tuple[Citation, ...]
    reply_pairs: tuple[tuple[str, str], ...]
    incomplete: bool
    pilot_eligible: bool
    limitations: tuple[str, ...]


def index_evidence(request: JudgeRequest, execution_mode: str) -> EvidenceIndex:
    refs, pairs, notes = [], [], []
    metric, sandbox = request.metric, request.sandbox
    incomplete = False
    if metric is None:
        incomplete = True
        notes.append(
            "Metric evidence is absent; no deterministic policy test conclusion is available."
        )
    else:
        clauses = (*metric.review.clauses, *metric.review.goals)
        unique([c.id for c in clauses])
        refs.extend(Citation(kind="policy_clause", id=c.id) for c in clauses)
        for case in metric.cases:
            refs.append(Citation(kind="metric_case", id=case.case_id))
            refs.extend(
                Citation(kind="metric_step", id=s.step_id, case_id=case.case_id)
                for s in case.trace
            )
        if metric.status != "completed" or not metric.cases or metric.unscored:
            incomplete = True
            notes.append(
                "Metric evidence is incomplete or includes unscored work; unscored does not mean passed."
            )
        if metric.generation_method == "authored_fixture":
            notes.append(
                "Supplied Metric cases are authored fixtures; no executed policy test is established by this input."
            )
        if metric.generation_method in {"policy_conditions", "policy_scenarios"}:
            notes.extend(metric.limitations)
        if metric.generation_method == "policy_conditions":
            notes.append(
                "Local comparison evidence supports reporting its test outcomes only. Judge's policy review remains qualitative: incomplete extraction cannot establish a missing provision, policy strength, defect or pilot recommendation."
            )
    if metric is None or metric.review.status != "ready":
        notes.append(
            "Judge review is qualitative only: no executable policy interpretation is available. Scenario questions and participant statements cannot establish policy pros, cons, omissions or approval readiness."
        )
    if sandbox is None:
        incomplete = True
        notes.append(
            "Sandbox evidence is absent; no stakeholder sentiment or interaction conclusion is available."
        )
    else:
        notes.extend(sandbox.limitations)
        personas = {p.persona_id for p in sandbox.personas}
        messages = {m.message_id: m for m in sandbox.messages}
        sources = {s.source_id: s for s in sandbox.sources}
        unique([p.persona_id for p in sandbox.personas])
        unique([m.message_id for m in sandbox.messages])
        unique([s.source_id for s in sandbox.sources])
        if sandbox.configured_stakeholder_count != len(
            personas
        ) or sandbox.observed_stakeholder_count != len(
            {m.persona_id for m in sandbox.messages}
        ):
            raise ValueError("Inconsistent Sandbox counts")
        if (
            sandbox.observed_stakeholder_count > sandbox.configured_stakeholder_count
            or sandbox.configured_stakeholder_count
            > sandbox.requested_stakeholder_count
        ):
            raise ValueError("Inconsistent Sandbox population")
        if [m.sequence for m in sandbox.messages] != list(range(1, len(messages) + 1)):
            raise ValueError("Ambiguous Sandbox ordering")
        seen = set()
        for m in sandbox.messages:
            if m.persona_id not in personas or set(m.source_refs) - sources.keys():
                raise ValueError("Unknown Sandbox author or source")
            unique(list(m.reply_to_message_ids))
            if set(m.reply_to_message_ids) - seen:
                raise ValueError("Unknown or unordered Sandbox reply")
            seen.add(m.message_id)
            if m.translation_status == "unavailable":
                incomplete = True
                continue
            refs.append(Citation(kind="sandbox_message", id=m.message_id))
            for parent in m.reply_to_message_ids:
                previous = messages[parent]
                if (
                    previous.translation_status != "unavailable"
                    and previous.persona_id != m.persona_id
                ):
                    pairs.append((parent, m.message_id))
        if any(s.record_id not in messages for s in sandbox.sources):
            raise ValueError("Unknown Sandbox source record")
        if (
            sandbox.status != "completed"
            or not sandbox.messages
            or sandbox.errors
            or sandbox.observed_stakeholder_count != sandbox.requested_stakeholder_count
        ):
            incomplete = True
        if sandbox.status != "completed" or not sandbox.messages or sandbox.errors:
            notes.append(
                "Sandbox evidence is incomplete; missing or untranslated records cannot establish stakeholder views."
            )
        if sandbox.observed_stakeholder_count != sandbox.requested_stakeholder_count:
            notes.append(
                f"Sandbox evidence contains messages from {sandbox.observed_stakeholder_count} of {sandbox.requested_stakeholder_count} requested stakeholders; population coverage is incomplete."
            )
        if any(m.translation_status == "unavailable" for m in sandbox.messages):
            notes.append(
                "Unavailable English translations are excluded from substantive citations and interaction pairs."
            )
        if sandbox.execution_mode == "fixture":
            notes.append(
                "Supplied Sandbox dialogue is an authored fixture, not a live MiroFish simulation."
            )
        elif sandbox.execution_mode == "recorded":
            notes.append(
                "Supplied Sandbox evidence is recorded; this Judge call did not launch a new simulation."
            )
        notes.append(
            "Simulated stakeholder statements are qualitative observations, not population statistics or verified policy facts."
        )
    if execution_mode == "fixture":
        notes.append(
            "Judge execution uses an explicitly configured fixture client; no live Judge provider was called."
        )
    elif execution_mode == "recorded":
        notes.append(
            "Judge execution uses a recorded client response; no new Judge provider call is established."
        )
    notes.append(
        "Advice is scoped to the supplied evidence. The full original policy text is not included in JudgeRequest."
    )
    eligible = bool(
        not incomplete
        and metric
        and sandbox
        and metric.passed > 0
        and metric.failed == 0
        and metric.generation_method != "authored_fixture"
        and sandbox.execution_mode != "fixture"
        and execution_mode != "fixture"
    )
    return EvidenceIndex(tuple(refs), tuple(pairs), incomplete, eligible, tuple(notes))


def validate_interactions(result, index):
    # The shared contract permits a lone message highlight. This adapter's
    # key_interactions deliberately require an actual cited cross-person reply.
    for finding in result.key_interactions:
        cited = {c.id for c in finding.citations if c.kind == "sandbox_message"}
        if not any({parent, reply} <= cited for parent, reply in index.reply_pairs):
            raise ValueError("Key interaction requires a cited, verified reply pair")
    for item in (
        *result.pros,
        *result.cons,
        *result.key_interactions,
        *result.next_steps,
    ):
        unique([(c.kind, c.id, c.case_id) for c in item.citations])


def label_mock_provenance(request: JudgeRequest, result: JudgeResult) -> JudgeResult:
    """Keep fixture provenance visible when the UI displays findings separately."""
    mock_stages = []
    if request.metric and request.metric.generation_method == "authored_fixture":
        mock_stages.append("Metric")
    if request.sandbox and request.sandbox.execution_mode == "fixture":
        mock_stages.append("Sandbox")
    if not mock_stages:
        return result
    data = result.model_dump(mode="json")

    def label(text, stages):
        prefix = f"Mock {' and '.join(stages)} evidence: " if stages else ""
        return text if text.startswith(prefix) else prefix + text

    data["summary"] = label(data["summary"], mock_stages)
    for field in ("pros", "cons", "key_interactions", "next_steps"):
        for finding in data[field]:
            kinds = {ref["kind"] for ref in finding["citations"]}
            stages = [
                stage
                for stage in mock_stages
                if not kinds
                or (stage == "Sandbox" and "sandbox_message" in kinds)
                or (stage == "Metric" and kinds - {"sandbox_message"})
            ]
            key = "reason" if field == "next_steps" else "text"
            finding[key] = label(finding[key], stages)
    return JudgeResult.model_validate(data)
