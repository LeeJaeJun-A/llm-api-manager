"""Trace / observation query endpoints (REQ-03).

Provides programmatic access to per-key usage history stored in Langfuse.
LiteLLM automatically sends traces to Langfuse with metadata including
the virtual key hash and customer ID, so we can filter by those.
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from httpx import HTTPStatusError

from app.dependencies import require_admin, require_customer
from app.services.langfuse_client import LangfuseClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["traces"])

_langfuse: LangfuseClient | None = None


def init_langfuse_client() -> LangfuseClient:
    global _langfuse
    _langfuse = LangfuseClient()
    return _langfuse


async def close_langfuse_client() -> None:
    global _langfuse
    if _langfuse:
        await _langfuse.close()
        _langfuse = None


def _get_langfuse() -> LangfuseClient:
    if _langfuse is None:
        raise RuntimeError("LangfuseClient not initialized")
    return _langfuse


@router.get("/customers/{customer_id}/traces")
async def list_customer_traces(
    customer_id: str,
    limit: int = Query(50, ge=1, le=200),
    page: int = Query(1, ge=1),
    from_timestamp: str | None = Query(None, description="ISO-8601 start"),
    to_timestamp: str | None = Query(None, description="ISO-8601 end"),
    caller_id: str = Depends(require_customer),
    langfuse: LangfuseClient = Depends(_get_langfuse),
):
    """List LLM call traces for a customer.

    LiteLLM tags each trace with `user_api_key_team_id` in metadata.
    We filter Langfuse traces by tag `team:{customer_id}` which LiteLLM
    automatically adds when the `team_id` is set on the virtual key.
    """
    if caller_id != customer_id:
        raise HTTPException(403, "Access denied to another customer's traces")

    try:
        result = await langfuse.list_traces(
            tags=[f"team_id:{customer_id}"],
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
            limit=limit,
            page=page,
        )
    except HTTPStatusError as exc:
        logger.error("Langfuse traces list failed: %s", exc.response.text)
        raise HTTPException(502, "Failed to fetch traces from Langfuse")
    except Exception:
        logger.exception("Unexpected error fetching traces")
        raise HTTPException(502, "Failed to fetch traces from Langfuse")

    traces = result.get("data", [])
    return {
        "customer_id": customer_id,
        "traces": [_slim_trace(t) for t in traces],
        "meta": result.get("meta", {}),
    }


@router.get("/customers/{customer_id}/traces/{trace_id}")
async def get_customer_trace(
    customer_id: str,
    trace_id: str,
    caller_id: str = Depends(require_customer),
    langfuse: LangfuseClient = Depends(_get_langfuse),
):
    """Get full trace detail including individual observations (LLM calls)."""
    if caller_id != customer_id:
        raise HTTPException(403, "Access denied to another customer's traces")

    try:
        trace = await langfuse.get_trace(trace_id)
    except HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(404, f"Trace {trace_id} not found")
        logger.error("Langfuse trace fetch failed: %s", exc.response.text)
        raise HTTPException(502, "Failed to fetch trace from Langfuse")

    trace_meta = trace.get("metadata") or {}
    if trace_meta.get("user_api_key_team_id") != customer_id:
        tags = trace.get("tags") or []
        if f"team_id:{customer_id}" not in tags:
            raise HTTPException(403, "This trace does not belong to your customer")

    observations_raw = []
    try:
        obs_resp = await langfuse.list_observations(trace_id=trace_id, limit=200)
        observations_raw = obs_resp.get("data", [])
    except Exception:
        logger.warning("Could not fetch observations for trace %s", trace_id)

    return {
        "customer_id": customer_id,
        "trace": _full_trace(trace, observations_raw),
    }


@router.get("/keys/{key_hash}/traces")
async def list_key_traces(
    key_hash: str,
    limit: int = Query(50, ge=1, le=200),
    page: int = Query(1, ge=1),
    from_timestamp: str | None = Query(None, description="ISO-8601 start"),
    to_timestamp: str | None = Query(None, description="ISO-8601 end"),
    _: None = Depends(require_admin),
    langfuse: LangfuseClient = Depends(_get_langfuse),
):
    """List traces for a specific virtual key (admin only).

    LiteLLM stores `user_api_key_hash` in trace metadata.
    We use the Langfuse `userId` field which LiteLLM sets to the key hash.
    """
    try:
        result = await langfuse.list_traces(
            user_id=key_hash,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
            limit=limit,
            page=page,
        )
    except HTTPStatusError as exc:
        logger.error("Langfuse key traces failed: %s", exc.response.text)
        raise HTTPException(502, "Failed to fetch traces from Langfuse")

    return {
        "key_hash": key_hash,
        "traces": [_slim_trace(t) for t in result.get("data", [])],
        "meta": result.get("meta", {}),
    }


def _slim_trace(t: dict[str, Any]) -> dict[str, Any]:
    """Extract key fields from a Langfuse trace for list responses."""
    return {
        "id": t.get("id"),
        "name": t.get("name"),
        "timestamp": t.get("timestamp"),
        "latency": t.get("latency"),
        "total_cost": t.get("totalCost"),
        "input_tokens": _extract_tokens(t, "input"),
        "output_tokens": _extract_tokens(t, "output"),
        "total_tokens": _extract_tokens(t, "total"),
        "tags": t.get("tags", []),
        "metadata": t.get("metadata"),
        "status": t.get("status"),
    }


def _full_trace(t: dict[str, Any], observations: list[dict]) -> dict[str, Any]:
    """Full trace with nested observation details."""
    base = _slim_trace(t)
    base["input"] = t.get("input")
    base["output"] = t.get("output")
    base["observations"] = [_slim_observation(o) for o in observations]
    return base


def _slim_observation(o: dict[str, Any]) -> dict[str, Any]:
    usage = o.get("usage") or {}
    return {
        "id": o.get("id"),
        "name": o.get("name"),
        "type": o.get("type"),
        "model": o.get("model"),
        "start_time": o.get("startTime"),
        "end_time": o.get("endTime"),
        "latency_ms": _calc_latency_ms(o),
        "input_tokens": usage.get("input"),
        "output_tokens": usage.get("output"),
        "total_tokens": usage.get("total"),
        "cost": o.get("calculatedTotalCost"),
        "input": o.get("input"),
        "output": o.get("output"),
        "status_message": o.get("statusMessage"),
        "level": o.get("level"),
    }


def _extract_tokens(t: dict, key: str) -> int | None:
    usage = t.get("usage") or t.get("totalUsage") or {}
    return usage.get(key)


def _calc_latency_ms(o: dict) -> float | None:
    start = o.get("startTime")
    end = o.get("endTime")
    if not start or not end:
        return None
    try:
        s = datetime.fromisoformat(start.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end.replace("Z", "+00:00"))
        return (e - s).total_seconds() * 1000
    except Exception:
        return None
