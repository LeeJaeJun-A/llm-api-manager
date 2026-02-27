import copy
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from app.config import get_settings


class ProviderCredential(BaseModel):
    provider: str = Field(
        ...,
        description="Provider 이름 (openai, anthropic, gemini, bedrock)",
    )
    api_key: str | None = Field(
        None,
        description="Provider API 키 (Anthropic, OpenAI, Gemini 등)",
    )
    aws_access_key_id: str | None = Field(None, description="Bedrock용")
    aws_secret_access_key: str | None = Field(None, description="Bedrock용")
    aws_region_name: str | None = Field(None, description="Bedrock용")

    @model_validator(mode="after")
    def _check_required_fields(self) -> "ProviderCredential":
        p = self.provider.lower()
        if p == "bedrock":
            if not self.aws_access_key_id or not self.aws_secret_access_key:
                raise ValueError(
                    "bedrock provider requires aws_access_key_id and aws_secret_access_key"
                )
        elif p in ("openai", "anthropic", "gemini"):
            if not self.api_key:
                raise ValueError(f"{p} provider requires api_key")
        return self


@lru_cache
def _load_provider_models_cached() -> dict[str, list[dict[str, str]]]:
    settings = get_settings()
    path = Path(settings.provider_models_path)
    if not path.exists():
        path = Path(__file__).resolve().parent.parent.parent / "provider_models.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def load_provider_models() -> dict[str, list[dict[str, str]]]:
    """
    Load the provider-model catalog from an external YAML file.
    Returns a deep copy to prevent mutation of cached data.
    """
    return copy.deepcopy(_load_provider_models_cached())


INTERNAL_PREFIX = "_cust_"


def internal_model_name(customer_id: str, base_name: str) -> str:
    """Hidden internal model name scoped to a customer."""
    return f"{INTERNAL_PREFIX}{customer_id}_{base_name}"


def is_internal_model(name: str) -> bool:
    return name.startswith(INTERNAL_PREFIX)


def base_name_from_internal(name: str, customer_id: str) -> str:
    """Extract the customer-facing model name from an internal name."""
    prefix = f"{INTERNAL_PREFIX}{customer_id}_"
    if name.startswith(prefix):
        return name[len(prefix):]
    return name


def build_aliases_for_customer(
    customer_id: str, model_names: list[str]
) -> dict[str, str]:
    """
    Build a key-level alias map from internal model names.

    Returns: {"gemini-pro": "_cust_customerA_gemini-pro", ...}
    so the customer calls model="gemini-pro" and LiteLLM resolves it.
    """
    aliases: dict[str, str] = {}
    prefix = f"{INTERNAL_PREFIX}{customer_id}_"
    for name in model_names:
        if name.startswith(prefix):
            customer_facing = name[len(prefix):]
            aliases[customer_facing] = name
    return aliases


class CustomerModelView(BaseModel):
    model_name: str = Field(..., description="호출 시 사용할 모델명 (예: gemini-pro)")
    role: str = Field(..., description="모델 역할 (reasoning / general)")
    provider: str
    owns_key: bool = Field(..., description="고객사 자체 키 여부 (false=플랫폼 키)")


class CredentialEventView(BaseModel):
    id: int
    customer_id: str
    provider: str
    action: str
    detail: dict | None = None
    created_at: str
