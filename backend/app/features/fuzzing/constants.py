"""Hard scenario-generation budgets and supported fact domains."""

MAX_SCENARIOS = 15
MAX_TARGETED_SCENARIOS = 5
INITIAL_SCENARIO_BUDGET = 10
INITIAL_EXPLORATORY_REQUEST = 3

INTEGER_FIELD_MAXIMUMS = {
    "amount_minor": 10_000_000,
    "booking_days_before": 365,
    "prior_same_day_category_spend_minor": 10_000_000,
    "daily_category_total_minor": 20_000_000,
}
