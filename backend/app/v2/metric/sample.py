"""Explicitly synthetic policy for the bounded reimbursement example."""

from app.v2.run_models import RunPolicyInput

SAMPLE_POLICY_TEXT = """POLICY_FORMAT=1
CLAUSE C-AMOUNT | per_claim_limit_cents=10000 | Claim amounts must be positive and no greater than the configured per-claim limit.
CLAUSE C-ALLOWANCE | participant_allowance_cents=15000 | Each participant has a separate configured total payment allowance.
CLAUSE C-APPROVAL-BUDGET | approval_budget_accounting=paid_only | Approval budget checks use the configured accounting basis.
CLAUSE C-PAYMENT-RECHECK | payment_budget_recheck=off | Payment uses the configured allowance recheck setting.
CLAUSE C-DUPLICATE | duplicate_scope=claim_id | Duplicate rejection uses the configured identity scope for the same participant.
CLAUSE C-LIFECYCLE | actions=submit,approve,pay,cancel | Claims follow ordered submission, approval, payment, and cancellation rules.
GOAL G-BUDGET | C-ALLOWANCE,C-APPROVAL-BUDGET,C-PAYMENT-RECHECK | Total participant payouts must not exceed that participant's allowance.
GOAL G-JOURNEY | C-DUPLICATE | A participant must receive at most one payment for the same journey.
GOAL G-CANCELLED | C-LIFECYCLE | A cancelled claim must not be paid.
GOAL G-LONE-VALID | C-AMOUNT,C-ALLOWANCE,C-LIFECYCLE | A lone valid claim within the limits can be paid.
GOAL G-AMOUNT | C-AMOUNT | No payment may occur for a claim outside the stated amount bounds."""

SAMPLE_POLICY = RunPolicyInput(
    title="Synthetic transport reimbursement policy",
    description=SAMPLE_POLICY_TEXT,
    agent_seed="Use varied synthetic commuter circumstances without expected outcomes.",
    agent_count=4,
)

__all__ = ["SAMPLE_POLICY", "SAMPLE_POLICY_TEXT"]
