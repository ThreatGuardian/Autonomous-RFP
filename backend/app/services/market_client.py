"""HTTP client for the competitor market API.

When ``TD_MARKET_API_URL`` is set the client calls that service over the
network; otherwise it calls the bundled mock through an in-process ASGI
transport. Either way the request/response contract is identical.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings


class MarketUnavailable(RuntimeError):
    pass


class InProcessTransport(httpx.BaseTransport):
    """Synchronous transport that dispatches requests to an ASGI app in-process."""

    def __init__(self, app) -> None:
        self._transport = httpx.ASGITransport(app=app)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        async def _send() -> httpx.Response:
            response = await self._transport.handle_async_request(request)
            content = await response.aread()
            return httpx.Response(response.status_code, headers=response.headers, content=content, request=request)

        return asyncio.run(_send())


@dataclass
class MarketResponse:
    offers: dict[str, list[dict[str, Any]]]
    endpoint: str
    latency_ms: int
    attempts: int


class MarketClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        settings = get_settings()
        self._headers = {"X-Api-Key": settings.market_api_key}
        if client is not None:
            self._client, self._endpoint = client, str(client.base_url)
        elif settings.market_api_url:
            self._client = httpx.Client(base_url=settings.market_api_url, timeout=8.0)
            self._endpoint = settings.market_api_url
        else:
            from app.market.service import market_app

            self._client = httpx.Client(transport=InProcessTransport(market_app), base_url="http://market.internal")
            self._endpoint = "in-process mock (http://market.internal)"

    def batch_offers(self, country: str, items: list[tuple[str, int]], retries: int = 2) -> MarketResponse:
        payload = {"country": country, "items": [{"mpn": m, "quantity": q} for m, q in items]}
        last: Exception | None = None
        t0 = time.perf_counter()
        for attempt in range(1, retries + 2):
            try:
                resp = self._client.post("/v1/offers/batch", json=payload, headers=self._headers)
                resp.raise_for_status()
                return MarketResponse(resp.json(), self._endpoint, int((time.perf_counter() - t0) * 1000), attempt)
            except (httpx.HTTPError, ValueError) as exc:
                last = exc
                time.sleep(0.2 * attempt)
        raise MarketUnavailable(f"Market API unavailable after {retries + 1} attempts: {last}")

    def competitors(self) -> list[dict[str, Any]]:
        resp = self._client.get("/v1/competitors", headers=self._headers)
        resp.raise_for_status()
        return resp.json()
