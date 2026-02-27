"""Customer credential management.

When a customer registers their own provider API key:
1. Internal model entries are created in LiteLLM (e.g. _cust_{customer_id}_gemini-pro)
2. Customer model list is updated (platform names swapped for internal names)
3. All existing keys get aliases updated so calling code stays the same
4. An audit event is recorded

The customer always calls model="gemini-pro" -- the key-level alias transparently
routes to the internal model that uses the customer's own API key.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from httpx import HTTPStatusError

from app.config import get_settings
from app.dependencies import get_litellm_client, require_customer
from app.schemas.model import (
    CustomerModelView,
    ProviderCredential,
    build_aliases_for_team,
    internal_model_name,
    load_provider_models,
)
from app.services import audit
from app.services.litellm_client import LiteLLMClient

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/customers/{customer_id}/credentials",
    tags=["credentials"],
)


# ── helpers ─────────────────────────────────────────


def _litellm_params(credential: ProviderCredential, litellm_model: str) -> dict:
    params: dict = {"model": litellm_model}
    if credential.provider == "bedrock":
        if credential.aws_access_key_id:
            params["aws_access_key_id"] = credential.aws_access_key_id
        if credential.aws_secret_access_key:
            params["aws_secret_access_key"] = credential.aws_secret_access_key
        if credential.aws_region_name:
            params["aws_region_name"] = credential.aws_region_name
    else:
        if credential.api_key:
            params["api_key"] = credential.api_key
    return params


async def _sync_key_aliases(
    client: LiteLLMClient, customer_id: str, models: list[str]
) -> int:
    """Rebuild aliases on every existing key for this customer."""
    aliases = build_aliases_for_team(customer_id, models)
    try:
        result = await client.list_keys(team_id=customer_id)
    except HTTPStatusError:
        return 0

    raw_keys = result if isinstance(result, list) else result.get("keys", [])
    updated = 0
    for k in raw_keys:
        key_token = k if isinstance(k, str) else (k.get("token") or k.get("key"))
        if not key_token:
            continue
        try:
            await client.update_key(key_token, {"aliases": aliases})
            updated += 1
        except HTTPStatusError:
            pass
    return updated


async def _delete_internal_models(
    client: LiteLLMClient, customer_id: str, provider: str
) -> None:
    """Remove LiteLLM model entries that belong to this customer+provider."""
    model_defs = load_provider_models().get(provider, [])
    target_names = {internal_model_name(customer_id, d["name"]) for d in model_defs}

    try:
        all_models = await client.list_models()
    except HTTPStatusError:
        return

    entries = all_models.get("data", []) if isinstance(all_models, dict) else all_models
    for entry in entries:
        if entry.get("model_name") in target_names:
            model_id = entry.get("model_info", {}).get("id")
            if model_id:
                try:
                    await client.delete_model(model_id)
                except HTTPStatusError:
                    pass


# ── endpoints ───────────────────────────────────────


@router.post("")
async def register_credential(
    customer_id: str,
    credential: ProviderCredential,
    caller_id: str = Depends(require_customer),
    client: LiteLLMClient = Depends(get_litellm_client),
):
    """고객사 자체 provider API 키 등록."""
    if customer_id != caller_id:
        raise HTTPException(status_code=403, detail="Cannot modify another team")

    provider = credential.provider.lower()
    catalog = load_provider_models()
    if provider not in catalog:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider. Supported: {', '.join(catalog)}",
        )

    model_defs = catalog[provider]

    await _delete_internal_models(client, customer_id, provider)

    created_names: list[str] = []
    for mdef in model_defs:
        int_name = internal_model_name(customer_id, mdef["name"])
        params = _litellm_params(credential, mdef["litellm_model"])
        try:
            await client.add_model({
                "model_name": int_name,
                "litellm_params": params,
                "model_info": {
                    "description": f"Customer key for {customer_id}",
                },
            })
            created_names.append(int_name)
        except HTTPStatusError as exc:
            try:
                all_models = await client.list_models()
                entries = all_models.get("data", []) if isinstance(all_models, dict) else all_models
                rollback_set = set(created_names)
                for entry in entries:
                    if entry.get("model_name") in rollback_set:
                        mid = entry.get("model_info", {}).get("id")
                        if mid:
                            await client.delete_model(mid)
            except HTTPStatusError:
                logger.warning("Failed to rollback models: %s", created_names)
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=f"Failed to register model {mdef['name']}: {exc}. "
                f"Rolled back {len(created_names)} previously created models.",
            )

    current_models = await client.get_team_models(customer_id)
    platform_names = {d["name"] for d in model_defs}
    internal_names = [internal_model_name(customer_id, d["name"]) for d in model_defs]

    updated = [m for m in current_models if m not in internal_names]
    for iname in internal_names:
        if iname not in updated:
            updated.append(iname)

    try:
        await client.update_team(customer_id, {"models": updated})
    except HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))

    keys_updated = await _sync_key_aliases(client, customer_id, updated)

    await audit.log_event(
        team_id=customer_id,
        provider=provider,
        action="register",
        detail={
            "models": [d["name"] for d in model_defs],
            "keys_updated": keys_updated,
        },
    )

    logger.info("Registered %s credential for customer %s", provider, customer_id)
    return {
        "detail": f"Registered customer {provider} key",
        "provider": provider,
        "models": [d["name"] for d in model_defs],
        "keys_updated": keys_updated,
    }


@router.delete("/{provider}")
async def deregister_credential(
    customer_id: str,
    provider: str,
    caller_id: str = Depends(require_customer),
    client: LiteLLMClient = Depends(get_litellm_client),
):
    """고객사 자체 provider 키 제거. 플랫폼 기본 키로 자동 복원."""
    if customer_id != caller_id:
        raise HTTPException(status_code=403, detail="Cannot modify another team")

    provider = provider.lower()
    catalog = load_provider_models()
    if provider not in catalog:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    model_defs = catalog[provider]

    await _delete_internal_models(client, customer_id, provider)

    current_models = await client.get_team_models(customer_id)
    internal_names = {internal_model_name(customer_id, d["name"]) for d in model_defs}
    platform_names = [d["name"] for d in model_defs]

    updated = [m for m in current_models if m not in internal_names]
    for pn in platform_names:
        if pn not in updated:
            updated.append(pn)

    try:
        await client.update_team(customer_id, {"models": updated})
    except HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))

    keys_updated = await _sync_key_aliases(client, customer_id, updated)

    await audit.log_event(
        team_id=customer_id,
        provider=provider,
        action="deregister",
        detail={
            "restored_to": "platform_key",
            "models": [d["name"] for d in model_defs],
            "keys_updated": keys_updated,
        },
    )

    logger.info("Deregistered %s credential for customer %s", provider, customer_id)
    return {
        "detail": f"Removed customer {provider} key, restored to platform default",
        "provider": provider,
        "models": platform_names,
        "keys_updated": keys_updated,
    }


@router.get("")
async def list_credentials(
    customer_id: str,
    caller_id: str = Depends(require_customer),
    client: LiteLLMClient = Depends(get_litellm_client),
):
    """고객사 모델 목록 (플랫폼 키 / 자체 키 구분 표시)."""
    if customer_id != caller_id:
        raise HTTPException(status_code=403, detail="Cannot view another team")

    current_models = await client.get_team_models(customer_id)

    platform_lookup: dict[str, dict] = {}
    for prov, defs in load_provider_models().items():
        for d in defs:
            platform_lookup[d["name"]] = {"provider": prov, "role": d["role"]}

    prefix = f"_cust_{customer_id}_"
    result: list[CustomerModelView] = []
    for name in current_models:
        if name.startswith(prefix):
            base = name[len(prefix):]
            meta = platform_lookup.get(base, {"provider": "unknown", "role": "unknown"})
            result.append(CustomerModelView(
                model_name=base, role=meta["role"], provider=meta["provider"], owns_key=True,
            ))
        else:
            meta = platform_lookup.get(name, {"provider": "unknown", "role": "unknown"})
            result.append(CustomerModelView(
                model_name=name, role=meta["role"], provider=meta["provider"], owns_key=False,
            ))

    return {"customer_id": customer_id, "models": result}


@router.get("/history")
async def credential_history(
    customer_id: str,
    provider: str | None = None,
    caller_id: str = Depends(require_customer),
):
    """자격증명 변경 이력 조회."""
    if customer_id != caller_id:
        raise HTTPException(status_code=403, detail="Cannot view another team")

    settings = get_settings()
    events = await audit.get_history(
        customer_id, provider=provider, limit=settings.audit_history_default_limit
    )
    return {"customer_id": customer_id, "events": events}
