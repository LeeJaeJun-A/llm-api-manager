from pydantic import BaseModel, Field


class UsageResponse(BaseModel):
    key: str = Field(..., description="키 해시 (ID)")
    key_alias: str | None = None
    customer_id: str | None = Field(None, description="고객사 ID")
    spend: float = Field(0.0, description="현재 누적 사용 비용 (USD)")
    max_budget: float | None = Field(None, description="예산 한도 (null=무제한)")
    budget_remaining: float | None = Field(
        None,
        description="남은 예산 (null=무제한이거나 한도 미설정)",
    )
    budget_duration: str | None = None
    tpm_limit: int | None = None
    rpm_limit: int | None = None
    models: list[str] = []
