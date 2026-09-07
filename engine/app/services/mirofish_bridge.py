"""Build a MiroFish seed + prompt from PolicyIR / ScenarioSuite, optionally launch."""

from __future__ import annotations

from app.contracts.common import now_iso
from app.contracts.mirofish import MiroFishLaunch, MiroFishPack
from app.contracts.policy import PolicyIR
from app.contracts.run import SeedSpec
from app.contracts.scenario import Scenario, ScenarioSuite


def build_mirofish_pack(
    ir: PolicyIR,
    seed: SeedSpec,
    suite: ScenarioSuite | None = None,
    *,
    max_agents: int = 50,
) -> MiroFishPack:
    cap = max(1, min(max_agents, 50))
    agents = (suite.scenarios if suite else [])[:cap]
    population = min(
        cap,
        (suite.population_size if suite and suite.population_size else None)
        or seed.population_size
        or len(agents)
        or cap,
    )
    return MiroFishPack(
        seed_markdown=_seed_markdown(ir, seed, agents, population),
        simulation_requirement=_simulation_requirement(ir, seed, population, len(agents)),
        population_size=population,
        agent_count=len(agents),
    )


def launch_mirofish(
    pack: MiroFishPack,
    *,
    policy_filename: str,
    policy_bytes: bytes,
    base_url: str,
    timeout: float = 120.0,
    client: "httpx.Client | None" = None,
) -> MiroFishLaunch:
    """POST seed + policy into MiroFish ontology/generate. Does not wait for the full sim."""
    import httpx

    url = base_url.rstrip("/") + "/api/graph/ontology/generate"
    files = [
        ("files", (pack.seed_filename, pack.seed_markdown.encode("utf-8"), "text/markdown")),
        ("files", (policy_filename, policy_bytes, "text/plain")),
    ]
    data = {
        "simulation_requirement": pack.simulation_requirement,
        "project_name": f"Policy rehearsal — {policy_filename}",
        "additional_context": (
            f"Population size {pack.population_size}. "
            "Agents in the seed document should become simulation personas."
        ),
    }
    owns_client = client is None
    http = client or httpx.Client(timeout=timeout)
    try:
        response = http.post(url, data=data, files=files, timeout=timeout)
        payload = response.json() if response.content else {}
        if response.is_success and payload.get("success"):
            project_id = (payload.get("data") or {}).get("project_id")
            return MiroFishLaunch(
                attempted=True,
                ok=True,
                project_id=project_id,
                mirofish_url=base_url.rstrip("/"),
                at=now_iso(),
            )
        error = payload.get("error") or response.text[:500] or f"HTTP {response.status_code}"
        return MiroFishLaunch(
            attempted=True,
            ok=False,
            error=str(error),
            mirofish_url=base_url.rstrip("/"),
            at=now_iso(),
        )
    except Exception as error:
        return MiroFishLaunch(
            attempted=True,
            ok=False,
            error=str(error),
            mirofish_url=base_url.rstrip("/"),
            at=now_iso(),
        )
    finally:
        if owns_client:
            http.close()


def _seed_markdown(
    ir: PolicyIR,
    seed: SeedSpec,
    agents: list[Scenario],
    population: int,
) -> str:
    lines = [
        f"# {ir.title}",
        "",
        "## Policy announcement",
        ir.source.text.strip() or ir.title,
        "",
        "## Public rules (compiled)",
    ]
    for rule in ir.rules:
        lines.append(f"- **{rule.id}** ({rule.then[0].modality if rule.then else 'rule'}): {rule.statement}")
    if ir.open_questions:
        lines.extend(["", "## Ambiguities the public may argue about"])
        for question in ir.open_questions:
            lines.append(f"- {question}")
    lines.extend(
        [
            "",
            "## Population seed",
            seed.text.strip() or "No extra census notes.",
            f"- Requested population size: {population}",
            f"- Groups: {', '.join(seed.groups) if seed.groups else 'unspecified'}",
            f"- Locale: {seed.locale or 'unspecified'}",
            "",
        ]
    )
    if seed.segments:
        lines.extend(["## Audience segments"])
        for segment in seed.segments:
            label = segment.label or segment.id
            attrs = ", ".join(f"{k}={v}" for k, v in list(segment.attributes.items())[:6])
            lines.append(
                f"- **{label}** (id={segment.id}, weight={segment.weight})"
                + (f" — {attrs}" if attrs else "")
            )
        lines.append("")
    lines.extend(
        [
            f"## Named residents ({len(agents) if agents else population})",
            "Each resident is an independent person with opinions. They talk to each other on social media.",
            "",
        ]
    )
    if agents:
        for index, scenario in enumerate(agents, start=1):
            lines.extend(_agent_block(index, scenario))
    else:
        count = population or 8
        groups = seed.groups or ["resident"]
        for index in range(1, count + 1):
            group = groups[(index - 1) % len(groups)]
            lines.extend(
                [
                    f"### Resident {index:03d}",
                    f"- Group: {group}",
                    f"- Persona: A {group.replace('_', ' ')} in this community. "
                    "They hear the policy announcement and discuss it with neighbours online.",
                    "",
                ]
            )
    return "\n".join(lines).strip() + "\n"


def _agent_block(index: int, scenario: Scenario) -> list[str]:
    facts = scenario.facts
    name = str(facts.get("actor.name") or scenario.title)
    role = (
        facts.get("actor.segment")
        or facts.get("actor.group")
        or facts.get("actor.role")
        or "resident"
    )
    age = facts.get("actor.age")
    action = facts.get("action.name") or "react"
    amount = facts.get("action.amount")
    lines = [
        f"### {index:03d}. {name}",
        f"- Test aim: {scenario.kind}",
        f"- Audience segment: {role}",
    ]
    if age is not None:
        lines.append(f"- Age: {age}")
    skip = {
        "actor.name", "actor.role", "actor.group", "actor.segment", "actor.age",
        "action.name", "action.amount", "context.location", "context.locale",
    }
    for key, value in facts.items():
        if key in skip or value in ("", None):
            continue
        if key.startswith(("actor.", "context.")) and not isinstance(value, (dict, list)):
            lines.append(f"- {key.split('.', 1)[1].replace('_', ' ').title()}: {value}")
    lines.append(f"- Intended action: {action}" + (f" (amount {amount})" if amount is not None else ""))
    if scenario.narrative:
        lines.append(f"- Situation: {scenario.narrative}")
    lines.append(
        f"- Persona: {name} is a {role} who will publicly discuss this policy. "
        f"Their scenario aim is {scenario.kind}. They post, comment, and argue with other residents."
    )
    lines.append("")
    return lines


def _simulation_requirement(
    ir: PolicyIR,
    seed: SeedSpec,
    population: int,
    agent_count: int,
) -> str:
    rule_lines = "\n".join(f"- {rule.statement}" for rule in ir.rules[:12])
    question_lines = "\n".join(f"- {question}" for question in ir.open_questions[:12])
    n = min(agent_count or population or 50, 50)
    return (
        f"A government just announced this policy: {ir.title}.\n\n"
        f"Key rules the public has heard:\n{rule_lines}\n\n"
        f"Open questions from the source:\n{question_lines or '- None recorded.'}\n\n"
        f"Simulate social-media reaction among {n} residents described in the seed "
        "for about 24 hours (keep the run short). Agents must talk to each other "
        "through posts, comments, and quote-tweets.\n\n"
        "Track support, opposition, perceived fairness, implementation concerns, "
        "and uncertainty about any open questions actually present in the source.\n\n"
        "Do not only restate the rules. Show how different groups react to one another. "
        "Do not invent eligibility categories, compensation programs, benefits, penalties, "
        "rumours, or other provisions that the policy does not state. If a participant "
        "raises an unsupported claim, label it as uncertainty or a question rather than fact.\n\n"
        f"Population notes: {seed.text.strip() or 'see seed document.'}"
    )
