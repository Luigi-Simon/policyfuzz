import json
from types import SimpleNamespace

import pytest

from app.v2.contracts import make_example_request
from app.v2.sandbox.language import (
    LanguageError,
    OpenAILanguageTools,
    Roster,
    RosterReview,
    TranslationReview,
)
from app.v2.sandbox.personas import SeedPersona, persona_payload
from app.v2.sandbox.translation import EnglishText


class SDK:
    def __init__(self, results):
        self.results, self.calls = iter(results), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(parse=self.parse))

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        result = next(self.results)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop", message=SimpleNamespace(parsed=result)
                )
            ]
        )


def test_persona_input_keeps_seed_and_count_independent_of_test_scenarios():
    request = make_example_request()
    payload = persona_payload(request, 3)
    assert payload["personality_seed"] == request.personality_seed
    assert payload["random_seed"] == request.random_seed
    assert payload["stakeholder_count"] == 3
    assert payload["policy_text"] == request.policy_text
    assert "test_budget" not in payload and "scenario_setups" not in payload


@pytest.mark.asyncio
async def test_roster_is_seed_bound_english_and_exact_count():
    people = [
        SeedPersona(
            display_name=f"Rider {i}",
            description=f"Practical safety-conscious worker {i}",
            opening_statement="How will it work?",
        )
        for i in range(3)
    ]
    sdk = SDK(
        [
            Roster(personas=people),
            RosterReview(english=True, seed_constraints_preserved=True),
        ]
    )
    tools = OpenAILanguageTools(model="fake-model", client=sdk)
    result = await tools.personas(make_example_request(), 3)
    assert result == tuple(people)
    payload = json.loads(sdk.calls[0]["messages"][1]["content"])
    assert payload["personality_seed"] == make_example_request().personality_seed
    assert "scenario_setups" not in payload


@pytest.mark.asyncio
async def test_wrong_roster_count_fails_before_launch():
    sdk = SDK([Roster(personas=[])])
    with pytest.raises(LanguageError, match="roster_invalid"):
        await OpenAILanguageTools(model="fake-model", client=sdk).personas(
            make_example_request(), 3
        )


@pytest.mark.asyncio
async def test_reviewer_rejects_changed_negation():
    sdk = SDK(
        [
            EnglishText(
                text="Reimbursement is allowed without a receipt.",
                language="Chinese",
                translated=True,
            ),
            TranslationReview(english=True, meaning_preserved=False),
        ]
    )
    with pytest.raises(LanguageError, match="translation_rejected"):
        await OpenAILanguageTools(model="fake-model", client=sdk).english(
            "没有收据不得报销。"
        )
    # Only human-readable strings enter either translation request.
    assert set(json.loads(sdk.calls[0]["messages"][1]["content"])) == {"text"}
    assert set(json.loads(sdk.calls[1]["messages"][1]["content"])) == {
        "source",
        "english",
    }


@pytest.mark.asyncio
async def test_reviewed_translation_of_eligibility_retains_number():
    english = "Only residents aged 18 and above are eligible."
    sdk = SDK(
        [
            EnglishText(text=english, language="Chinese", translated=True),
            TranslationReview(english=True, meaning_preserved=True),
        ]
    )
    result = await OpenAILanguageTools(model="fake-model", client=sdk).english(
        "仅限18岁及以上居民。"
    )
    assert result.text == english and len(sdk.calls) == 2


@pytest.mark.asyncio
async def test_refusal_or_missing_parsed_response_is_sanitized():
    with pytest.raises(LanguageError, match="language_provider_failed"):
        await OpenAILanguageTools(model="fake-model", client=SDK([None])).english(
            "Hello"
        )
