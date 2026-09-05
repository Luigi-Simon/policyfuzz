# Policy Intelligence supported vocabulary

This is a development target for the compiler prompts. It is not a replacement for the frozen shared contracts.

## Predicate fields

`employee_role`, `expense_category`, `amount_minor`, `destination_type`, `booking_days_before`, `receipt_present`, `approval_roles_present`, and `prior_same_day_category_spend_minor`.

The invariant-only derived field is `daily_category_total_minor`; executable policy rules must not use it.

## Operators

Categorical fields: `eq`, `neq`, `in`, `not_in`.

Numeric fields: `eq`, `neq`, `lt`, `lte`, `gt`, `gte`.

Boolean fields: `eq`, `neq`.

Approval-role sets: `contains`.

Conditions use AND semantics. OR prose becomes separate rules.

## Effect dimensions

`eligibility` (`allow`, `deny`), `receipt_requirement` (`required`, `not_required`), `approval_requirement` (`none`, `manager`, `director`, `finance`), `claim_cap_minor` (non-negative integer), and `daily_category_cap_minor` (non-negative integer).

## Exceptions and unsupported clauses

The compiler may represent an exception only when its trigger and effect are explicit and typed. Vague language such as “reasonable,” “at management discretion,” or “as required by law” is preserved as an unsupported clause with its exact source span and a reason code; it must not be silently converted into an executable rule.
