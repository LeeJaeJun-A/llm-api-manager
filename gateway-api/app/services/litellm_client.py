import logging
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class LiteLLMClient:
    """Async wrapper around the LiteLLM Proxy Admin API.

    Uses a shared httpx.AsyncClient for connection pooling.
    Call close() or use as async context manager to release resources.
    """

    def __init__(self, settings: Settings | None = None):
        s = settings or get_settings()
        self._client = httpx.AsyncClient(
            base_url=s.litellm_base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {s.litellm_master_key}",
                "Content-Type": "application/json",
            },
            timeout=s.litellm_client_timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
    ) -> Any:
        resp = await self._client.request(method, path, json=json, params=params)
        resp.raise_for_status()
        return resp.json()

    # ── Customer (LiteLLM team API) ─────────────────

    async def create_customer(self, data: dict) -> dict:
        return await self._request("POST", "/team/new", json=data)

    async def list_customers(self) -> list[dict]:
        return await self._request("GET", "/team/list")

    async def get_customer(self, customer_id: str) -> dict:
        return await self._request(
            "GET", "/team/info", params={"team_id": customer_id}
        )

    async def update_customer(self, customer_id: str, data: dict) -> dict:
        data = {**data, "team_id": customer_id}
        return await self._request("POST", "/team/update", json=data)

    async def delete_customer(self, customer_id: str) -> dict:
        return await self._request(
            "POST", "/team/delete", json={"team_ids": [customer_id]}
        )

    # ── Key ─────────────────────────────────────────

    async def generate_key(self, data: dict) -> dict:
        return await self._request("POST", "/key/generate", json=data)

    async def list_keys(self, customer_id: str | None = None) -> dict:
        params = {}
        if customer_id:
            params["team_id"] = customer_id
        return await self._request("GET", "/key/list", params=params)

    async def get_key(self, key: str) -> dict:
        return await self._request("GET", "/key/info", params={"key": key})

    async def update_key(self, key: str, data: dict) -> dict:
        data["key"] = key
        return await self._request("POST", "/key/update", json=data)

    async def delete_key(self, key: str) -> dict:
        return await self._request("POST", "/key/delete", json={"keys": [key]})

    # ── Model ───────────────────────────────────────

    async def add_model(self, data: dict) -> dict:
        return await self._request("POST", "/model/new", json=data)

    async def list_models(self) -> dict:
        return await self._request("GET", "/model/info")

    async def get_model(self, model_id: str) -> dict:
        return await self._request(
            "GET", "/model/info", params={"litellm_model_id": model_id}
        )

    async def delete_model(self, model_id: str) -> dict:
        return await self._request(
            "POST", "/model/delete", json={"id": model_id}
        )

    # ── Helpers ──────────────────────────────────────

    async def get_customer_models(self, customer_id: str) -> list[str]:
        """Fetch the current model list for a customer."""
        info = await self.get_customer(customer_id)
        team_info = info.get("team_info", info)
        return team_info.get("models") or []
