import logging

from fastapi import APIRouter, Depends, HTTPException
from httpx import HTTPStatusError

from app.dependencies import get_litellm_client, require_customer
from app.schemas.usage import CustomerUsageResponse, KeyUsageSummary, UsageResponse
from app.services.litellm_client import LiteLLMClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["usage"])


@router.get("/usage/{key_id}", response_model=UsageResponse)
async def get_usage(
    key_id: str,
    customer_id: str = Depends(require_customer),
    client: LiteLLMClient = Depends(get_litellm_client),
):
    """키별 현재 사용량 + 남은 할당량 조회."""
    try:
        result = await client.get_key(key_id)
    except HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))

    info = result.get("info", result)
    if info.get("team_id") != customer_id:
        raise HTTPException(status_code=403, detail="Key does not belong to your customer")

    spend = info.get("spend", 0.0)
    max_budget = info.get("max_budget")
    budget_remaining = None
    if max_budget is not None:
        budget_remaining = max(0.0, max_budget - spend)

    return UsageResponse(
        key=key_id,
        key_alias=info.get("key_alias"),
        customer_id=info.get("team_id"),
        spend=spend,
        max_budget=max_budget,
        budget_remaining=budget_remaining,
        budget_duration=info.get("budget_duration"),
        tpm_limit=info.get("tpm_limit"),
        rpm_limit=info.get("rpm_limit"),
        models=info.get("models") or [],
    )


@router.get("/customers/{customer_id}/usage", response_model=CustomerUsageResponse)
async def get_customer_usage(
    customer_id: str,
    caller_id: str = Depends(require_customer),
    client: LiteLLMClient = Depends(get_litellm_client),
):
    """고객 전체 사용량 조회: 총 사용액, 한도, 잔액 + 키별 내역."""
    if caller_id != customer_id:
        raise HTTPException(403, "Access denied to another customer's usage")

    try:
        team_result = await client.get_customer(customer_id)
    except HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))

    team_info = team_result.get("team_info", team_result)
    team_spend = team_info.get("spend", 0.0) or 0.0
    team_max_budget = team_info.get("max_budget")
    team_budget_duration = team_info.get("budget_duration")

    team_remaining = None
    if team_max_budget is not None:
        team_remaining = max(0.0, team_max_budget - team_spend)

    try:
        keys_result = await client.list_keys(customer_id=customer_id)
    except HTTPStatusError as exc:
        logger.warning("Failed to list keys for customer %s: %s", customer_id, exc.response.text)
        keys_result = []

    raw_keys = keys_result if isinstance(keys_result, list) else keys_result.get("keys", [])

    key_summaries: list[KeyUsageSummary] = []
    for k in raw_keys:
        if isinstance(k, str):
            try:
                key_info_resp = await client.get_key(k)
                k = key_info_resp.get("info", key_info_resp)
            except Exception:
                continue

        k_spend = k.get("spend", 0.0) or 0.0
        k_max = k.get("max_budget")
        k_remaining = None
        if k_max is not None:
            k_remaining = max(0.0, k_max - k_spend)

        key_summaries.append(
            KeyUsageSummary(
                key=k.get("token") or k.get("key") or "",
                key_alias=k.get("key_alias"),
                spend=k_spend,
                max_budget=k_max,
                budget_remaining=k_remaining,
                models=k.get("models") or [],
            )
        )

    return CustomerUsageResponse(
        customer_id=customer_id,
        customer_alias=team_info.get("team_alias"),
        total_spend=team_spend,
        max_budget=team_max_budget,
        budget_remaining=team_remaining,
        budget_duration=team_budget_duration,
        tpm_limit=team_info.get("tpm_limit"),
        rpm_limit=team_info.get("rpm_limit"),
        keys=key_summaries,
    )
