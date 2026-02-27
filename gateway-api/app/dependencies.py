from fastapi import Depends, Header, HTTPException, status

from app.config import Settings, get_settings
from app.services.litellm_client import LiteLLMClient

_litellm_client: LiteLLMClient | None = None


def init_litellm_client() -> LiteLLMClient:
    global _litellm_client
    _litellm_client = LiteLLMClient()
    return _litellm_client


async def close_litellm_client() -> None:
    global _litellm_client
    if _litellm_client:
        await _litellm_client.close()
        _litellm_client = None


async def require_admin(
    x_api_secret: str = Header(..., alias="X-API-Secret"),
    settings: Settings = Depends(get_settings),
) -> None:
    """Validate that the caller holds the gateway admin secret."""
    if x_api_secret != settings.gateway_api_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API secret",
        )


async def require_customer(
    x_api_secret: str = Header(..., alias="X-API-Secret"),
    x_customer_id: str = Header(..., alias="X-Customer-Id"),
    settings: Settings = Depends(get_settings),
) -> str:
    """Validate customer credentials and return the customer_id."""
    if x_api_secret != settings.gateway_api_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API secret",
        )
    return x_customer_id


def get_litellm_client() -> LiteLLMClient:
    if _litellm_client is None:
        raise RuntimeError("LiteLLMClient not initialized")
    return _litellm_client
