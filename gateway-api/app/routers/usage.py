from fastapi import APIRouter, Depends, HTTPException
from httpx import HTTPStatusError

from app.dependencies import get_litellm_client, require_customer
from app.schemas.usage import UsageResponse
from app.services.litellm_client import LiteLLMClient

router = APIRouter(prefix="/api/v1/usage", tags=["usage"])


@router.get("/{key_id}", response_model=UsageResponse)
async def get_usage(
    key_id: str,
    team_id: str = Depends(require_customer),
    client: LiteLLMClient = Depends(get_litellm_client),
):
    """키별 현재 사용량 + 남은 할당량 조회. REQ-02."""
    try:
        result = await client.get_key(key_id)
    except HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))

    info = result.get("info", result)
    if info.get("team_id") != team_id:
        raise HTTPException(status_code=403, detail="Key does not belong to your team")

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
