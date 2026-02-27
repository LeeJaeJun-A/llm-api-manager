"""Async client for querying Langfuse REST API (traces / observations)."""

import logging
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class LangfuseClient:
    """Queries Langfuse public API using Basic auth (public_key:secret_key)."""

    def __init__(self, settings: Settings | None = None):
        s = settings or get_settings()
        self._client = httpx.AsyncClient(
            base_url=s.langfuse_host.rstrip("/"),
            auth=(s.langfuse_public_key, s.langfuse_secret_key),
            timeout=s.litellm_client_timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict | None = None) -> Any:
        resp = await self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def list_traces(
        self,
        *,
        user_id: str | None = None,
        tags: list[str] | None = None,
        name: str | None = None,
        from_timestamp: str | None = None,
        to_timestamp: str | None = None,
        limit: int = 50,
        page: int = 1,
        order_by: str | None = None,
    ) -> dict:
        """GET /api/public/traces with optional filters."""
        params: dict[str, Any] = {"limit": limit, "page": page}
        if user_id:
            params["userId"] = user_id
        if tags:
            for tag in tags:
                params.setdefault("tags", []).append(tag)
        if name:
            params["name"] = name
        if from_timestamp:
            params["fromTimestamp"] = from_timestamp
        if to_timestamp:
            params["toTimestamp"] = to_timestamp
        if order_by:
            params["orderBy"] = order_by
        return await self._get("/api/public/traces", params=params)

    async def get_trace(self, trace_id: str) -> dict:
        """GET /api/public/traces/{traceId}."""
        return await self._get(f"/api/public/traces/{trace_id}")

    async def list_observations(
        self,
        *,
        trace_id: str | None = None,
        name: str | None = None,
        type: str | None = None,
        limit: int = 50,
        page: int = 1,
    ) -> dict:
        """GET /api/public/observations — individual LLM calls within a trace."""
        params: dict[str, Any] = {"limit": limit, "page": page}
        if trace_id:
            params["traceId"] = trace_id
        if name:
            params["name"] = name
        if type:
            params["type"] = type
        return await self._get("/api/public/observations", params=params)
