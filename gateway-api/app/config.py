import logging
from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # ── Gateway API ─────────────────────────────────
    gateway_api_port: int = 8000
    gateway_api_secret: str

    # ── LiteLLM Proxy ──────────────────────────────
    litellm_base_url: str = "http://litellm-proxy:4000"
    litellm_master_key: str

    @model_validator(mode="after")
    def _check_secrets(self) -> "Settings":
        if not self.gateway_api_secret:
            raise ValueError("GATEWAY_API_SECRET must be set")
        if not self.litellm_master_key:
            raise ValueError("LITELLM_MASTER_KEY must be set")
        return self
    litellm_client_timeout: float = 30.0

    # ── Langfuse ────────────────────────────────────
    langfuse_host: str = "http://langfuse:3000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    # ── Database (audit log) ───────────────────────
    database_url: str = ""
    db_pool_min_size: int = 1
    db_pool_max_size: int = 5

    # ── Audit ──────────────────────────────────────
    audit_history_default_limit: int = 100

    # ── Provider models config ─────────────────────
    provider_models_path: str = "/app/provider_models.yaml"

    model_config = {"env_file": ".env"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
