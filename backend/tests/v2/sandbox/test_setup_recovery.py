import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from openai import AuthenticationError, RateLimitError

from app.v2.contracts import make_example_request
from app.v2.sandbox.language import (
    LanguageError,
    OpenAILanguageTools,
    Roster,
    RosterReview,
)
from app.v2.sandbox.personas import SeedPersona


def people(start, count):
    return [
        SeedPersona(
            display_name=f"Resident {i}",
            description="A practical resident with caring responsibilities.",
            opening_statement="How would this affect my schedule?",
        )
        for i in range(start, start + count)
    ]


class Client:
    def __init__(self, values):
        self.values, self.calls = iter(values), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(parse=self.parse))

    async def parse(self, **kw):
        self.calls.append(kw)
        value = next(self.values)
        if isinstance(value, BaseException):
            raise value
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(parsed=value, refusal=None),
                )
            ]
        )


OK = RosterReview(english=True, seed_constraints_preserved=True)


@pytest.mark.asyncio
async def test_twenty_people_are_generated_in_small_exact_distinct_batches():
    client = Client(
        [item for n in range(0, 20, 5) for item in (Roster(personas=people(n, 5)), OK)]
    )
    result = await OpenAILanguageTools(model="fake", client=client).personas(
        make_example_request(), 20
    )
    assert len(result) == len({p.display_name for p in result}) == 20
    generated = [
        json.loads(c["messages"][1]["content"])
        for c in client.calls
        if c["response_format"] is Roster
    ]
    assert [p["stakeholder_count"] for p in generated] == [5] * 4
    assert generated[-1]["excluded_names"] == [p.display_name for p in result[:15]]


@pytest.mark.asyncio
async def test_invalid_count_is_repaired_before_native_launch():
    client = Client([Roster(personas=[]), Roster(personas=people(0, 3)), OK])
    result = await OpenAILanguageTools(model="fake", client=client).personas(
        make_example_request(), 3
    )
    assert len(result) == 3
    assert json.loads(client.calls[1]["messages"][1]["content"])["repair_codes"] == [
        "roster_count"
    ]


@pytest.mark.asyncio
async def test_authentication_errors_are_sanitized_and_not_retried():
    error = AuthenticationError(
        "secret raw provider body",
        response=httpx.Response(401, request=httpx.Request("POST", "http://provider")),
        body=None,
    )
    client = Client([error])
    with pytest.raises(LanguageError) as caught:
        await OpenAILanguageTools(model="fake", client=client).personas(
            make_example_request(), 3
        )
    assert caught.value.code == "provider_authentication"
    assert "secret" not in str(caught.value) and len(client.calls) == 1


@pytest.mark.asyncio
async def test_transient_provider_error_retries_within_bound():
    error = RateLimitError(
        "secret",
        response=httpx.Response(429, request=httpx.Request("POST", "http://provider")),
        body=None,
    )
    client = Client([error, Roster(personas=people(0, 3)), OK])
    result = await OpenAILanguageTools(
        model="fake", client=client, retry_delay=0
    ).personas(make_example_request(), 3)
    assert len(result) == 3 and len(client.calls) == 3


@pytest.mark.asyncio
async def test_cancellation_is_never_swallowed_or_retried():
    client = Client([asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError):
        await OpenAILanguageTools(model="fake", client=client).personas(
            make_example_request(), 3
        )
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_seed_review_failure_is_explicit_after_bounded_repairs():
    client = Client(
        [
            item
            for _ in range(3)
            for item in (
                Roster(personas=people(0, 3)),
                RosterReview(english=True, seed_constraints_preserved=False),
            )
        ]
    )
    with pytest.raises(LanguageError) as caught:
        await OpenAILanguageTools(model="fake", client=client).personas(
            make_example_request(), 3
        )
    assert caught.value.code == "roster_seed_review" and len(client.calls) == 6


@pytest.mark.asyncio
async def test_refusal_is_not_retried():
    class Refusal(Client):
        async def parse(self, **kw):
            self.calls.append(kw)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason="stop",
                        message=SimpleNamespace(parsed=None, refusal="Refused"),
                    )
                ]
            )

    client = Refusal([])
    with pytest.raises(LanguageError) as caught:
        await OpenAILanguageTools(model="fake", client=client).personas(
            make_example_request(), 3
        )
    assert caught.value.code == "provider_refusal" and len(client.calls) == 1


@pytest.mark.asyncio
async def test_server_retry_after_is_respected_or_retry_is_skipped(monkeypatch):
    sleeps = []

    async def sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    for delay in (3, 3600):
        error = RateLimitError(
            "private",
            response=httpx.Response(
                429,
                headers={"retry-after": str(delay)},
                request=httpx.Request("POST", "http://provider"),
            ),
            body=None,
        )
        client = Client([error, Roster(personas=people(0, 3)), OK])
        language = OpenAILanguageTools(model="fake", client=client, retry_delay=0)
        if delay == 3:
            assert len(await language.personas(make_example_request(), 3)) == 3
            assert sleeps == [3]
        else:
            with pytest.raises(LanguageError):
                await language.personas(make_example_request(), 3)
            assert len(client.calls) == 1 and sleeps == [3]


@pytest.mark.asyncio
async def test_duplicate_across_batches_is_repaired_without_regenerating_accepted_people():
    client = Client(
        [
            Roster(personas=people(0, 5)),
            OK,
            Roster(personas=people(0, 1)),
            Roster(personas=people(5, 1)),
            OK,
        ]
    )
    result = await OpenAILanguageTools(model="fake", client=client).personas(
        make_example_request(), 6
    )
    assert len(result) == len({p.display_name for p in result}) == 6
    assert json.loads(client.calls[3]["messages"][1]["content"])["repair_codes"] == [
        "roster_duplicate"
    ]
