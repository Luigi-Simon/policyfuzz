import pytest
from pydantic import ValidationError

from app.domain.models import (
    AddOverrideOperation,
    FindingDecision,
    PatchAcceptanceReport,
    RevisionProposal,
)

from .factories import HASH, make_inputs


def operation():
    return AddOverrideOperation(
        rule_id="rule-meal",
        dimension="claim_cap_minor",
        target_rule_id="rule-general",
        finding_ids=("finding-gap",),
    )


def proposal(operations):
    return RevisionProposal(
        proposal_id="proposal-1",
        document_sha256=HASH,
        rule_set_sha256=HASH,
        policy_contract_sha256=HASH,
        suite_sha256=HASH,
        accepted_finding_ids=("finding-gap",),
        operations=operations,
        draft_policy_wording="Require receipts.",
    )


@pytest.mark.parametrize("count", [0, 4])
def test_revision_has_one_to_three_operations(count):
    with pytest.raises(ValidationError):
        proposal(tuple(operation() for _ in range(count)))


def test_revision_only_targets_accepted_findings():
    with pytest.raises(ValidationError):
        proposal((operation().model_copy(update={"finding_ids": ("unaccepted",)}),))
    assert proposal((operation(),)).operations[0].rule_id == "rule-meal"


def test_finding_decision_rejects_unknown_reviewer_severity():
    with pytest.raises(ValidationError):
        FindingDecision(
            finding_id="finding-gap", decision="accept", reviewer_severity="urgent"
        )
    assert (
        FindingDecision(
            finding_id="finding-gap", decision="accept", reviewer_severity="high"
        ).reviewer_severity
        == "high"
    )


FLAGS = (
    "suite_hash_matches",
    "all_target_findings_fixed",
    "zero_new_failures_outside_targets",
    "zero_protected_regressions",
    "no_increase_in_gap_conflict_inconclusive_or_error",
    "unrelated_rules_unchanged",
    "holdout_not_worse",
)


@pytest.mark.parametrize("failed_flag", FLAGS)
def test_every_acceptance_boolean_is_required(failed_flag):
    values = dict.fromkeys(FLAGS, True) | {failed_flag: False}
    with pytest.raises(ValidationError):
        PatchAcceptanceReport(
            baseline_inputs=make_inputs(),
            revised_inputs=make_inputs(),
            **values,
            patch_accepted=True,
        )
    assert not PatchAcceptanceReport(
        baseline_inputs=make_inputs(),
        revised_inputs=make_inputs(),
        **values,
        patch_accepted=False,
    ).patch_accepted


def test_acceptance_cannot_disagree_with_successful_checks():
    with pytest.raises(ValidationError):
        PatchAcceptanceReport(
            baseline_inputs=make_inputs(),
            revised_inputs=make_inputs(),
            **dict.fromkeys(FLAGS, True),
            patch_accepted=False,
        )
    assert PatchAcceptanceReport(
        baseline_inputs=make_inputs(),
        revised_inputs=make_inputs(),
        **dict.fromkeys(FLAGS, True),
        patch_accepted=True,
    ).patch_accepted


def test_patch_acceptance_declares_exact_comparison_inputs():
    with pytest.raises(ValidationError):
        PatchAcceptanceReport(**dict.fromkeys(FLAGS, True), patch_accepted=True)


def test_revision_rule_drafts_cannot_add_catchall_or_derived_conditions():
    from app.domain.models import Effect, Predicate, RevisionRuleDraft

    for conditions in (
        (),
        (Predicate(field="daily_category_total_minor", operator="gt", value=5000),),
    ):
        with pytest.raises(ValidationError):
            RevisionRuleDraft(
                description="Unsupported broadened rule",
                when=conditions,
                effects=(Effect(dimension="claim_cap_minor", value=5000),),
            )


def test_regression_requires_frozen_suite_engine_contract_and_manifest():
    from app.domain.models import (
        AssertionTransitionCounts,
        EffectStateCounts,
        RegressionReport,
    )

    from .factories import make_inputs

    for field in (
        "suite_sha256",
        "engine_sha256",
        "contract_sha256",
        "run_manifest_sha256",
    ):
        with pytest.raises(ValidationError):
            RegressionReport(
                report_id="r1",
                baseline_inputs=make_inputs(),
                revised_inputs=make_inputs(**{field: "b" * 64}),
                baseline_effect_states=EffectStateCounts(),
                revised_effect_states=EffectStateCounts(),
                assertion_transition_counts=AssertionTransitionCounts(),
                assertion_transitions=(),
            )
