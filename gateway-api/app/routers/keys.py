import logging

from fastapi import APIRouter, Depends, HTTPException
from httpx import HTTPStatusError

from app.dependencies import get_litellm_client, require_customer

logger = logging.getLogger(__name__)
from app.schemas.key import KeyCreateRequest, KeyResponse, KeyUpdateRequest
from app.schemas.model import build_aliases_for_team
from app.services.litellm_client import LiteLLMClient

router = APIRouter(prefix="/api/v1/keys", tags=["keys"])


@router.post("", response_model=KeyResponse)
async def create_key(
    body: KeyCreateRequest,
    team_id: str = Depends(require_customer),
    client: LiteLLMClient = Depends(get_litellm_client),
):
    """
    키 발급 (team_id + TPM/RPM/예산 설정). REQ-01, REQ-04.

    고객사가 자체 provider 키를 등록한 경우, 해당 모델에 대한
    aliases가 자동 설정되어 호출부에 변화 없이 동작합니다.
    """
    if body.customer_id != team_id:
        raise HTTPException(status_code=403, detail="Cannot create keys for another team")

    models = await client.get_team_models(team_id)
    aliases = build_aliases_for_team(team_id, models)

    payload: dict = {"team_id": body.customer_id}
    if aliases:
        payload["aliases"] = aliases
    if body.key_alias is not None:
        payload["key_alias"] = body.key_alias
    if body.models is not None:
        payload["models"] = body.models
    if body.tpm_limit is not None:
        payload["tpm_limit"] = body.tpm_limit
    if body.rpm_limit is not None:
        payload["rpm_limit"] = body.rpm_limit
    if body.max_budget is not None:
        payload["max_budget"] = body.max_budget
    if body.budget_duration is not None:
        payload["budget_duration"] = body.budget_duration
    if body.duration is not None:
        payload["duration"] = body.duration
    if body.metadata is not None:
        payload["metadata"] = body.metadata

    try:
        result = await client.generate_key(payload)
    except HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))

    return _to_key_response(result)


@router.get("")
async def list_keys(
    team_id: str = Depends(require_customer),
    client: LiteLLMClient = Depends(get_litellm_client),
):
    """내 team에 속한 키 목록 조회."""
    try:
        result = await client.list_keys(team_id=team_id)
    except HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))

    raw_keys = result if isinstance(result, list) else result.get("keys", [])
    key_responses = []
    for k in raw_keys:
        if isinstance(k, str):
            try:
                info_result = await client.get_key(k)
                info = info_result.get("info", info_result)
                key_responses.append(_to_key_response(info))
            except HTTPStatusError:
                continue
        else:
            key_responses.append(_to_key_response(k))
    return {"keys": key_responses}


@router.get("/{key_id}", response_model=KeyResponse)
async def get_key(
    key_id: str,
    team_id: str = Depends(require_customer),
    client: LiteLLMClient = Depends(get_litellm_client),
):
    """키 상세 + 사용량 조회."""
    try:
        result = await client.get_key(key_id)
    except HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))

    info = result.get("info", result)
    if info.get("team_id") != team_id:
        raise HTTPException(status_code=403, detail="Key does not belong to your team")

    return _to_key_response(info)


@router.patch("/{key_id}", response_model=KeyResponse)
async def update_key(
    key_id: str,
    body: KeyUpdateRequest,
    team_id: str = Depends(require_customer),
    client: LiteLLMClient = Depends(get_litellm_client),
):
    """키 Limit 수정. REQ-04."""
    try:
        info_result = await client.get_key(key_id)
    except HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))

    info = info_result.get("info", info_result)
    if info.get("team_id") != team_id:
        raise HTTPException(status_code=403, detail="Key does not belong to your team")

    payload = body.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        result = await client.update_key(key_id, payload)
    except HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))

    return _to_key_response(result)


@router.delete("/{key_id}")
async def delete_key(
    key_id: str,
    team_id: str = Depends(require_customer),
    client: LiteLLMClient = Depends(get_litellm_client),
):
    """키 비활성화/삭제."""
    try:
        info_result = await client.get_key(key_id)
    except HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))

    info = info_result.get("info", info_result)
    if info.get("team_id") != team_id:
        raise HTTPException(status_code=403, detail="Key does not belong to your team")

    try:
        result = await client.delete_key(key_id)
    except HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))

    return result


def _to_key_response(data: dict) -> KeyResponse:
    return KeyResponse(
        token=data.get("token") or data.get("key"),
        key=data.get("key") or data.get("token"),
        key_alias=data.get("key_alias"),
        key_name=data.get("key_name"),
        customer_id=data.get("team_id"),
        models=data.get("models") or [],
        tpm_limit=data.get("tpm_limit"),
        rpm_limit=data.get("rpm_limit"),
        max_budget=data.get("max_budget"),
        budget_duration=data.get("budget_duration"),
        spend=data.get("spend", 0.0),
        expires=data.get("expires"),
        metadata=data.get("metadata"),
    )
