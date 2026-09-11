"""Explicit duration comparisons only; applicability and exceptions stay unscored.

This grammar does not infer a cap from a 'standard workweek', choose a blackout
implementation, interpret clock-window endpoints, or apply employment law.
"""

import re
from decimal import Decimal

from app.v2.metric_contracts import NumericCondition

LABELS = {
    "rest_minutes": "Rest duration in minutes",
    "notice_days": "Change notice in calendar days",
    "weekly_work_minutes": "Weekly working time in minutes",
}
LIMITATIONS = (
    "These are clause-local boundary checks of explicit duration comparisons in an interpreted model, not independent verification of policy correctness or workplace compliance.",
    "Rest hours use integer minutes and notice uses calendar days. Applicability, operational exceptions, opt-outs, retaliation, compensation, alternative implementations and combined policy outcomes remain unscored.",
    "Clock windows, timezone conversions and endpoint inclusivity require an explicit supported interpretation; they are scenario questions, not executed time-window tests. A standard workweek reference alone does not establish a maximum.",
)


def compile_employment(text, number, end, operators):
    import hashlib

    found = []
    for segment in re.finditer(r".+?(?:[.!?](?=\s|$)|\n|$)", text, re.DOTALL):
        sentence = segment.group()
        safe = re.sub(
            r"not exceed(?:ing)?|no (?:more|less) than",
            "",
            sentence,
            flags=re.IGNORECASE,
        )
        # 'may ... only with ... at least N days notice' states a necessary
        # local threshold. It does not make continuation or other clauses mandatory.
        conditional_permission = bool(
            re.search(r"\bmay\b[^.;!?]*\bonly with\b", safe, re.IGNORECASE)
        )
        if conditional_permission:
            safe = re.sub(
                r"\bmay\b(?=[^.;!?]*\bonly with\b)", "", safe, flags=re.IGNORECASE
            )
        if re.search(r"\b(not|no|may|might|example|unless)\b", safe, re.IGNORECASE):
            continue
        for op, expression in operators.items():
            for field, pattern, scale in (
                (
                    "rest_minutes",
                    rf"(?:{expression})\s+(?P<n>{number}){end}\s+(?:consecutive\s+)?hours?\s+(?:of\s+)?(?:uninterrupted,?\s+)?(?:offline\s+)?rest\b",
                    60,
                ),
                (
                    "notice_days",
                    rf"(?:{expression})\s+(?P<n>{number}){end}\s+(?:calendar\s+)?days?\s*['’]?\s+(?:of\s+)?notice\b",
                    1,
                ),
                (
                    "weekly_work_minutes",
                    rf"\bweekly\s+(?:working|work)\s+hours\s+(?:must\s+)?(?:{expression})\s+(?P<n>{number}){end}\s+hours?\b",
                    60,
                ),
            ):
                for match in re.finditer(rf"(?<!\w){pattern}", sentence, re.IGNORECASE):
                    if conditional_permission and (
                        field != "notice_days"
                        or not re.search(
                            r"\bonly with\b", sentence[: match.start()], re.IGNORECASE
                        )
                    ):
                        continue
                    # Fractional calendar days and sub-minute precision need a
                    # separate interpretation, never rounding or silent scaling.
                    value = Decimal(match["n"].replace(",", "")) * scale
                    if (
                        value != value.to_integral_value()
                        or not 0 <= value <= 100_000_000
                    ):
                        continue
                    start, stop = (
                        segment.start() + match.start(),
                        segment.start() + match.end(),
                    )
                    found.append(
                        NumericCondition(
                            id="R1",
                            clause_id="C-R1",
                            field=field,
                            operator=op,
                            threshold=int(value),
                            source_start=start,
                            source_end=stop,
                            source_sha256=hashlib.sha256(
                                text[start:stop].encode()
                            ).hexdigest(),
                        )
                    )
    # Longer operators win over suffixes, e.g. 'no less than' is >=,
    # never a second, contradictory '<' comparison on 'less than'.
    selected = []
    for condition in sorted(found, key=lambda c: (c.source_start, -c.source_end)):
        if any(
            condition.source_start < c.source_end
            and c.source_start < condition.source_end
            for c in selected
        ):
            continue
        selected.append(condition)
    return selected
