"""Trace / observation query endpoints.

Custom callback(litellm/custom_callbacks.py)이 모든 LLM 호출의 Langfuse trace에
userId = customer_id(team_id)를 자동 주입하므로,
list_traces(userId=customer_id)로 바로 고객별 trace를 조회할 수 있습니다.
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from httpx import HTTPStatusError

from app.dependencies import require_customer
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
    """고객의 LLM 호출 trace 목록 조회 (Langfuse userId = customer_id)."""
    if caller_id != customer_id:
        raise HTTPException(403, "Access denied to another customer's traces")

    try:
        result = await langfuse.list_traces(
            user_id=customer_id,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
            limit=limit,
            page=page,
        )
    except HTTPStatusError as exc:
        logger.error("Langfuse list_traces failed: %s", exc.response.text)
        raise HTTPException(502, "Failed to fetch traces from Langfuse")

    return {
        "customer_id": customer_id,
        "traces": [_slim_trace(t) for t in result.get("data", [])],
        "meta": result.get("meta", {}),
    }


@router.get("/customers/{customer_id}/traces/{trace_id}")
async def get_customer_trace(
    customer_id: str,
    trace_id: str,
    caller_id: str = Depends(require_customer),
    langfuse: LangfuseClient = Depends(_get_langfuse),
):
    """특정 trace 상세 조회 (개별 LLM 호출 observation 포함)."""
    if caller_id != customer_id:
        raise HTTPException(403, "Access denied to another customer's traces")

    try:
        trace = await langfuse.get_trace(trace_id)
    except HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(404, f"Trace {trace_id} not found")
        logger.error("Langfuse trace fetch failed: %s", exc.response.text)
        raise HTTPException(502, "Failed to fetch trace from Langfuse")

    if trace.get("userId") != customer_id:
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


# ── Response mappers ────────────────────────────────


def _slim_trace(t: dict[str, Any]) -> dict[str, Any]:
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
    }


def _full_trace(t: dict[str, Any], observations: list[dict]) -> dict[str, Any]:
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
