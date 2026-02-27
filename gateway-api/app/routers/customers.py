import logging

from fastapi import APIRouter, Depends, HTTPException
from httpx import HTTPStatusError

from app.dependencies import get_litellm_client, require_admin
from app.schemas.customer import (
    CustomerCreateRequest,
    CustomerResponse,
    CustomerUpdateRequest,
)
from app.services.litellm_client import LiteLLMClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])


@router.post("", response_model=CustomerResponse, dependencies=[Depends(require_admin)])
async def create_customer(
    body: CustomerCreateRequest,
    client: LiteLLMClient = Depends(get_litellm_client),
):
    """고객사 등록 및 허용 모델 목록 지정. customer_id가 LiteLLM team_id로 사용됩니다."""
    payload: dict = {
        "team_id": body.customer_id,
        "team_alias": body.customer_alias,
        "models": body.models,
    }
    if body.tpm_limit is not None:
        payload["tpm_limit"] = body.tpm_limit
    if body.rpm_limit is not None:
        payload["rpm_limit"] = body.rpm_limit
    if body.max_budget is not None:
        payload["max_budget"] = body.max_budget
    if body.budget_duration is not None:
        payload["budget_duration"] = body.budget_duration
    if body.metadata is not None:
        payload["metadata"] = body.metadata

    try:
        result = await client.create_customer(payload)
    except HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))

    return _to_customer_response(result)


@router.get("", dependencies=[Depends(require_admin)])
async def list_customers(
    client: LiteLLMClient = Depends(get_litellm_client),
):
    """전체 고객사 목록 조회."""
    try:
        result = await client.list_customers()
    except HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))

    teams = result if isinstance(result, list) else result.get("teams", [])
    return [_to_customer_response(t) for t in teams]


@router.get("/{customer_id}", response_model=CustomerResponse, dependencies=[Depends(require_admin)])
async def get_customer(
    customer_id: str,
    client: LiteLLMClient = Depends(get_litellm_client),
):
    """고객사 상세 조회 (할당 모델 포함)."""
    try:
        result = await client.get_customer(customer_id)
    except HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))

    info = result.get("team_info", result)
    return _to_customer_response(info)


@router.patch("/{customer_id}", response_model=CustomerResponse, dependencies=[Depends(require_admin)])
async def update_customer(
    customer_id: str,
    body: CustomerUpdateRequest,
    client: LiteLLMClient = Depends(get_litellm_client),
):
    """고객사 모델 목록 및 한도 수정."""
    payload = body.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        result = await client.update_customer(customer_id, payload)
    except HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))

    result_data = result.get("data", result)
    return _to_customer_response(result_data)


@router.delete("/{customer_id}", dependencies=[Depends(require_admin)])
async def delete_customer(
    customer_id: str,
    client: LiteLLMClient = Depends(get_litellm_client),
):
    """고객사 삭제."""
    try:
        result = await client.delete_customer(customer_id)
    except HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))

    return result


def _to_customer_response(data: dict) -> CustomerResponse:
    cid = data.get("team_id", "")
    return CustomerResponse(
        customer_id=cid,
        customer_alias=data.get("team_alias"),
        models=data.get("models") or [],
        tpm_limit=data.get("tpm_limit"),
        rpm_limit=data.get("rpm_limit"),
        max_budget=data.get("max_budget"),
        budget_duration=data.get("budget_duration"),
        spend=data.get("spend", 0.0),
        metadata=data.get("metadata"),
    )
