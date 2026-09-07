"""Turn EvaluationReport + optional swarm capture into a 0–100 effectiveness score."""

from __future__ import annotations

from typing import Any

from app.contracts.effectiveness import (
    AgentInteraction,
    PolicyEffectivenessReport,
    RevisionHint,
)
from app.contracts.evaluation import EvaluationReport
from app.contracts.policy import PolicyIR
from app.llm import LLMAdapter, LLMError

CONFUSION_MARKERS = (
    "confus", "rumour", "rumor", "unfair", "ineligible", "who gets",
    "not eligible", "angry", "protest", "scam", "loophole",
    "不公平", "困惑", "传言", "谣言", "为什么", "资格", "监护",
)
SUPPORT_MARKERS = ("support", "fair", "clear", "eligible", "thank", "好消息", "支持")


def synthesize_effectiveness(
    ir: PolicyIR,
    evaluation: EvaluationReport,
    *,
    swarm: dict[str, Any] | None = None,
    llm: LLMAdapter | None = None,
) -> PolicyEffectivenessReport:
    metrics = _metrics(ir, evaluation, swarm)
    score = _score(metrics)
    highlights = _highlights(swarm)
    hints = _hints(ir, evaluation, highlights)
    justification = _justification(ir, evaluation, metrics, highlights, score)
    if llm is not None and llm.enabled:
        try:
            refined = _llm_refine(ir, evaluation, metrics, highlights, score, hints, llm)
            score = int(refined.get("score", score))
            score = max(0, min(100, score))
            justification = str(refined.get("justification") or justification)
            extra_hints = refined.get("recommended_actions") or []
            if isinstance(extra_hints, list) and extra_hints:
                hints = _hints_from_llm(extra_hints) or hints
        except (LLMError, TypeError, ValueError, KeyError):
            pass
    justification = _ensure_conversations(justification, highlights)
    return PolicyEffectivenessReport(
        policy_id=ir.policy_id,
        policy_revision=ir.revision,
        score=score,
        justification=justification,
        highlights=highlights[:8],
        recommended_actions=hints[:6],
        swarm_used=bool(
            swarm and (swarm.get("actions") or swarm.get("posts") or swarm.get("comments"))
        ),
        interaction_verified=bool(swarm and (swarm.get("comments") or [])),
        metrics=metrics,
    )


def _metrics(
    ir: PolicyIR,
    evaluation: EvaluationReport,
    swarm: dict[str, Any] | None,
) -> dict[str, Any]:
    findings = evaluation.findings
    n = max(len(findings), 1)
    verdicts = {"pass": 0, "fail": 0, "ambiguous": 0, "error": 0}
    adversarial_fails = 0
    for finding in findings:
        verdicts[finding.verdict] = verdicts.get(finding.verdict, 0) + 1
        if finding.verdict == "fail" and "adversarial" in finding.summary:
            adversarial_fails += 1
    covered = {rule_id for finding in findings for rule_id in finding.rule_ids}
    actions = list((swarm or {}).get("actions") or [])
    posts = list((swarm or {}).get("posts") or [])
    comments = list((swarm or {}).get("comments") or [])
    texts = [_text_of(item) for item in [*posts, *comments, *actions]]
    confusion = sum(1 for text in texts if _has_marker(text, CONFUSION_MARKERS))
    support = sum(1 for text in texts if _has_marker(text, SUPPORT_MARKERS))
    return {
        "scenario_count": len(findings),
        "rule_count": len(ir.rules),
        "rules_covered": len(covered),
        "pass_rate": verdicts["pass"] / n,
        "fail_rate": verdicts["fail"] / n,
        "ambiguous_rate": verdicts["ambiguous"] / n,
        "adversarial_fails": adversarial_fails,
        "verdicts": verdicts,
        "swarm_actions": len(actions),
        "swarm_posts": len(posts),
        "swarm_comments": len(comments),
        "swarm_confusion_mentions": confusion,
        "swarm_support_mentions": support,
        "open_questions": len(ir.open_questions),
    }


def _score(metrics: dict[str, Any]) -> int:
    coverage = metrics["rules_covered"] / max(metrics["rule_count"], 1)
    raw = (
        100 * (0.50 * metrics["pass_rate"] + 0.20 * coverage + 0.15 * (1 - metrics["ambiguous_rate"]))
        - 25 * metrics["fail_rate"]
        - 4 * min(metrics["open_questions"], 5)
    )
    mentions = max(metrics["swarm_posts"] + metrics["swarm_comments"], 1)
    if metrics["swarm_actions"] or metrics["swarm_posts"]:
        confusion_ratio = metrics["swarm_confusion_mentions"] / mentions
        support_ratio = metrics["swarm_support_mentions"] / mentions
        raw += 10 * support_ratio - 18 * confusion_ratio
    return max(0, min(100, int(round(raw))))


def _highlights(swarm: dict[str, Any] | None) -> list[AgentInteraction]:
    if not swarm:
        return []
    items: list[AgentInteraction] = []
    comments = list(swarm.get("comments") or [])
    posts = list(swarm.get("posts") or [])
    for item in comments:
        text = _text_of(item)
        if not text:
            continue
        target = str(
            item.get("reply_to_name")
            or item.get("post_author")
            or item.get("parent_user_name")
            or ""
        )
        why = (
            f"Reply to {target}" if target else "Agent-to-agent reply in the swarm"
        )
        if _has_marker(text, CONFUSION_MARKERS):
            why += " — confusion / fairness challenge"
        items.append(
            AgentInteraction(
                agent=_agent_name(item),
                platform=str(item.get("platform") or "twitter"),
                kind="comment",
                text=text[:400],
                why_significant=why,
            )
        )
    for item in posts:
        text = _text_of(item)
        if not text:
            continue
        significant = _has_marker(text, CONFUSION_MARKERS + SUPPORT_MARKERS)
        why = (
            "Public confusion / fairness challenge"
            if _has_marker(text, CONFUSION_MARKERS)
            else "Opening post that other agents can reply to"
        )
        if significant or not comments:
            items.append(
                AgentInteraction(
                    agent=_agent_name(item),
                    platform=str(item.get("platform") or "twitter"),
                    kind="post",
                    text=text[:400],
                    why_significant=why,
                )
            )
    if items:
        return items
    for item in (swarm.get("actions") or [])[:8]:
        text = _text_of(item)
        if not text:
            continue
        items.append(
            AgentInteraction(
                agent=_agent_name(item),
                platform=str(item.get("platform") or ""),
                kind=str(item.get("action_type") or "action"),
                text=text[:400],
                why_significant="High-signal swarm action from the rehearsal.",
            )
        )
    return items


def _hints(
    ir: PolicyIR,
    evaluation: EvaluationReport,
    highlights: list[AgentInteraction],
) -> list[RevisionHint]:
    hints: list[RevisionHint] = []
    failed = [finding for finding in evaluation.findings if finding.verdict == "fail"]
    ambiguous = [finding for finding in evaluation.findings if finding.verdict == "ambiguous"]
    if failed:
        rule_ids = sorted({rid for finding in failed for rid in finding.rule_ids})[:4]
        hints.append(
            RevisionHint(
                rule_ids=rule_ids,
                action="tighten",
                summary=(
                    f"{len(failed)} fuzz cases failed. Tighten {', '.join(rule_ids) or 'the matched rules'} "
                    "so forbidden claims are rejected and eligible claims still pass."
                ),
            )
        )
    if ambiguous or ir.open_questions:
        hints.append(
            RevisionHint(
                rule_ids=list(ir.index.open_question_rule_ids)[:4],
                action="clarify",
                summary=(
                    "Spell out edge cases the public already argues about: "
                    + ("; ".join(ir.open_questions[:3]) or "see ambiguous findings.")
                ),
            )
        )
    if any("unfair" in (item.text + item.why_significant).lower() for item in highlights):
        hints.append(
            RevisionHint(
                rule_ids=[],
                action="communicate",
                summary="Swarm agents framed the policy as unfair. Add a plain-language eligibility explainer, not only a legal tweak.",
            )
        )
    if not hints:
        hints.append(
            RevisionHint(
                rule_ids=[],
                action="communicate",
                summary="Fuzz coverage looks stable. Publish a short FAQ covering who is in and who is out before launch.",
            )
        )
    return hints


def _justification(
    ir: PolicyIR,
    evaluation: EvaluationReport,
    metrics: dict[str, Any],
    highlights: list[AgentInteraction],
    score: int,
) -> str:
    parts = [
        f"Effectiveness score {score}/100 for “{ir.title}” (revision {ir.revision}).",
        (
            f"Fuzz suite: {metrics['scenario_count']} agents, "
            f"{metrics['verdicts']['pass']} pass / {metrics['verdicts']['fail']} fail / "
            f"{metrics['verdicts']['ambiguous']} ambiguous, covering "
            f"{metrics['rules_covered']}/{metrics['rule_count']} rules."
        ),
    ]
    notable = [finding for finding in evaluation.findings if finding.verdict in {"fail", "ambiguous"}][:3]
    for finding in notable:
        parts.append(f"- {finding.summary}")
    if highlights:
        comments = [item for item in highlights if item.kind == "comment"]
        posts = [item for item in highlights if item.kind == "post"]
        if comments:
            parts.append("Key swarm conversations:")
            for item in comments[:5]:
                parts.append(f"- {item.agent} ({item.why_significant}): {item.text[:220]}")
        if posts:
            parts.append("Posts other agents reacted to:")
            for item in posts[:4]:
                parts.append(f"- {item.agent} ({item.kind}): {item.text[:180]}")
                if item.why_significant and item.kind != "comment":
                    parts.append(f"  Why it matters: {item.why_significant}")
    elif not metrics["swarm_actions"] and not metrics["swarm_posts"]:
        parts.append(
            "No MiroFish swarm capture yet — this score is from the fuzz grader only. "
            "POST /v1/runs/{id}/rehearse?swarm=true with MiroFish running to ground it in agent talk."
        )
    return "\n".join(parts)


def _ensure_conversations(justification: str, highlights: list[AgentInteraction]) -> str:
    comments = [item for item in highlights if item.kind == "comment"]
    posts = [item for item in highlights if item.kind == "post"]
    extra: list[str] = []
    if comments and "Key swarm conversations" not in justification:
        extra.append("Key swarm conversations:")
        extra.extend(
            f"- {item.agent} ({item.why_significant}): {item.text[:220]}"
            for item in comments[:5]
        )
    if posts and "Posts other agents reacted to" not in justification:
        extra.append("Posts other agents reacted to:")
        extra.extend(f"- {item.agent}: {item.text[:180]}" for item in posts[:4])
    if not extra:
        return justification
    return justification.rstrip() + "\n\n" + "\n".join(extra)


def _llm_refine(
    ir: PolicyIR,
    evaluation: EvaluationReport,
    metrics: dict[str, Any],
    highlights: list[AgentInteraction],
    score: int,
    hints: list[RevisionHint],
    llm: LLMAdapter,
) -> dict[str, Any]:
    failures = [finding.summary for finding in evaluation.findings if finding.verdict == "fail"][:8]
    swarm_bits = [f"{item.agent}: {item.text}" for item in highlights[:6]]
    return llm.complete_json(
        system=(
            "You score how effective a public policy would be in the real world. "
            "Return JSON {score: 0-100 integer, justification: string, "
            "recommended_actions: [{rule_ids: [str], action: clarify|tighten|carve_out|add_rule|communicate, summary: str}]}. "
            "Keep the score within 15 points of the heuristic unless swarm evidence is overwhelming. "
            "Cite named agents. Quote 2-4 short conversation turns (who posted, who replied) when comments exist."
        ),
        user=(
            f"Title: {ir.title}\nHeuristic score: {score}\nMetrics: {metrics}\n"
            f"Open questions: {ir.open_questions}\nFailures:\n- "
            + "\n- ".join(failures or ["none"])
            + "\nSwarm:\n- "
            + "\n- ".join(swarm_bits or ["none"])
            + "\nDraft hints:\n- "
            + "\n- ".join(h.summary for h in hints)
        ),
    )


def _hints_from_llm(raw: list[Any]) -> list[RevisionHint]:
    hints: list[RevisionHint] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("summary"):
            continue
        action = item.get("action") or "clarify"
        if action not in {"clarify", "tighten", "carve_out", "add_rule", "communicate"}:
            action = "clarify"
        hints.append(
            RevisionHint(
                rule_ids=[str(rid) for rid in (item.get("rule_ids") or [])],
                action=action,
                summary=str(item["summary"]),
            )
        )
    return hints


def _agent_name(item: dict[str, Any]) -> str:
    return str(
        item.get("user_name")
        or item.get("agent_name")
        or item.get("username")
        or item.get("name")
        or item.get("agent_id")
        or "agent"
    )


def _text_of(item: dict[str, Any]) -> str:
    for key in ("content", "text", "body", "message", "action_args", "args"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = value.get("content") or value.get("text")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return ""


def _has_marker(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in markers)
