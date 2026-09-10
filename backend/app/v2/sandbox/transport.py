"""Async transport for the owned v2 extension plus native MiroFish capture APIs."""

import httpx

from .personas import SeedPersona


class MiroFishError(RuntimeError):
    pass


class MiroFishClient:
    max_agents = 50

    def __init__(
        self,
        base_url="http://127.0.0.1:5002",
        *,
        client=None,
        timeout_seconds=20,
        page_size=100,
        max_records=500,
    ):
        if not 1 <= page_size <= max_records <= 5000:
            raise ValueError("Invalid capture pagination bounds")
        self._owns_client = client is None
        self.http = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout_seconds
        )
        self.timeout = timeout_seconds
        self.page_size, self.max_records = page_size, max_records

    async def _request(self, method, path, *, missing_ok=False, **kwargs):
        try:
            response = await self.http.request(
                method, path, timeout=self.timeout, **kwargs
            )
            if response.status_code == 404 and missing_ok:
                # A missing extension route is not a missing job. The v2 extension
                # returns this exact machine code only for a known lookup endpoint.
                body = response.json()
                if isinstance(body, dict) and body.get("code") == "job_not_found":
                    return None
            response.raise_for_status()
            body = response.json()
            if (
                not isinstance(body, dict)
                or body.get("success") is not True
                or not isinstance(body.get("data"), dict)
            ):
                raise ValueError("Malformed envelope")
            return body["data"]
        except (httpx.HTTPError, ValueError, TypeError):
            raise MiroFishError(
                "mirofish_transport_failed: MiroFish returned an unavailable or invalid response."
            ) from None

    async def lookup(self, fingerprint):
        return await self._request(
            "GET", f"/api/policyfuzz/v2/jobs/{fingerprint}", missing_ok=True
        )

    async def prepare(self, request, personas):
        return await self._request(
            "POST",
            "/api/policyfuzz/v2/prepare",
            json={
                "request": request.model_dump(mode="json"),
                "personas": [
                    SeedPersona.model_validate(p).model_dump() for p in personas
                ],
            },
        )

    async def start(self, fingerprint):
        return await self._request(
            "POST",
            "/api/policyfuzz/v2/start",
            json={"request_fingerprint": fingerprint},
        )

    async def status(self, fingerprint):
        return await self._request("GET", f"/api/policyfuzz/v2/jobs/{fingerprint}")

    async def stop(self, fingerprint):
        return await self._request(
            "POST", "/api/policyfuzz/v2/stop", json={"request_fingerprint": fingerprint}
        )

    async def capture(self, simulation_id):
        from urllib.parse import quote

        captured, notes = {}, []
        # Each endpoint can fail independently without discarding earlier evidence.
        for kind in ("posts", "comments", "actions"):
            rows = captured[kind] = []
            try:
                for offset in range(0, self.max_records, self.page_size):
                    limit = min(self.page_size, self.max_records - offset)
                    page = await self._request(
                        "GET",
                        f"/api/simulation/{quote(simulation_id, safe='')}/{kind}",
                        params={
                            "platform": "twitter",
                            "limit": limit,
                            "offset": offset,
                        },
                    )
                    items = page.get(kind)
                    if not isinstance(items, list):
                        raise TypeError("Malformed page")
                    rows.extend(items[:limit])
                    if len(items) < limit:
                        break
                else:
                    notes.append(
                        f"capture_limit: {kind} reached the configured capture limit; further records may exist."
                    )
            except (MiroFishError, ValueError, TypeError):
                notes.append(
                    f"capture_endpoint_failed: Some {kind} could not be retrieved."
                )
        return captured, notes

    async def close(self):
        if self._owns_client:
            await self.http.aclose()
