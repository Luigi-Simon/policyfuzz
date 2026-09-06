"""Minimal ScenarioDesigner showing the person-3 plugin shape.

Run with:
  SCENARIO_DESIGNER=examples.simple_designer:SimpleDesigner
  uvicorn app.main:app --reload --port 8000
"""

from app.contracts.policy import PolicyIR
from app.contracts.run import SeedSpec
from app.contracts.scenario import Scenario, ScenarioSuite
from app.plugins.scenario_designer import ScenarioDesigner


class SimpleDesigner(ScenarioDesigner):
    def generate(self, ir: PolicyIR, seed: SeedSpec) -> ScenarioSuite:
        first_rule = ir.rules[0].id if ir.rules else "R001"
        first_actor = ir.actor_types[0].id if ir.actor_types else "subject"
        kinds = ("normal", "boundary", "adversarial", "targeted")
        scenarios = [
            Scenario(
                kind=kind,
                title=f"{kind} probe of {first_rule}",
                narrative=f"Seed={seed.text or 'none'}; replace this designer with the real fuzzer.",
                facts={
                    "actor.role": first_actor,
                    "action.name": ir.actions[0].name if ir.actions else "comply",
                    "context.location": "classroom",
                },
                targeted_rule_ids=[first_rule],
                expected_outcome="compliant" if kind == "normal" else "ambiguous",
            )
            for kind in kinds
        ]
        return ScenarioSuite(
            policy_id=ir.policy_id,
            policy_revision=ir.revision,
            seed=seed.text,
            population_size=seed.population_size,
            scenarios=scenarios,
        )
