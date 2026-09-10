import httpx
import pytest

from app.v2.sandbox.transport import MiroFishClient, MiroFishError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"success": False, "error": "秘密"}),
        httpx.Response(200, text="not json"),
        httpx.Response(503, text="provider token=secret"),
        httpx.Response(404, json={"error": "unknown route"}),
    ],
)
async def test_bad_envelopes_never_leak_raw_errors(response):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: response), base_url="http://fake"
    ) as http:
        with pytest.raises(MiroFishError) as exc:
            await MiroFishClient(client=http).lookup("a" * 64)
        assert "秘密" not in str(exc.value) and "secret" not in str(exc.value)


@pytest.mark.asyncio
async def test_only_explicit_missing_job_permits_prepare():
    response = httpx.Response(404, json={"success": False, "code": "job_not_found"})
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: response), base_url="http://fake"
    ) as http:
        assert await MiroFishClient(client=http).lookup("a" * 64) is None


@pytest.mark.asyncio
async def test_paginated_capture_preserves_successful_endpoints_and_bounds():
    offsets = []

    def handler(request):
        kind = request.url.path.rsplit("/", 1)[-1]
        offset = int(request.url.params["offset"])
        offsets.append((kind, offset))
        if kind == "comments":
            return httpx.Response(503)
        rows = [{"post_id": offset + i} for i in range(2)] if kind == "posts" else []
        return httpx.Response(200, json={"success": True, "data": {kind: rows}})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://fake"
    ) as http:
        rows, notes = await MiroFishClient(
            client=http, page_size=2, max_records=4
        ).capture("sim_1")
    assert len(rows["posts"]) == 4 and rows["comments"] == []
    assert offsets == [("posts", 0), ("posts", 2), ("comments", 0), ("actions", 0)]
    assert any(n.startswith("capture_limit:") for n in notes)
    assert any(n.startswith("capture_endpoint_failed:") for n in notes)


@pytest.mark.asyncio
async def test_injected_client_lifetime_remains_with_caller():
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200))
    )
    await MiroFishClient(client=http).close()
    assert not http.is_closed
    await http.aclose()
