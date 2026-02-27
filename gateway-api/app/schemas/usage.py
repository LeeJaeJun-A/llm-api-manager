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


class KeyUsageSummary(BaseModel):
    key: str = Field(..., description="키 토큰 또는 해시")
    key_alias: str | None = None
    spend: float = Field(0.0, description="이 키의 누적 사용 비용 (USD)")
    max_budget: float | None = Field(None, description="키 예산 한도 (null=무제한)")
    budget_remaining: float | None = Field(None, description="키 잔여 예산")
    models: list[str] = []


class CustomerUsageResponse(BaseModel):
    customer_id: str = Field(..., description="고객사 ID")
    customer_alias: str | None = None
    total_spend: float = Field(0.0, description="고객사 전체 누적 사용 비용 (USD)")
    max_budget: float | None = Field(None, description="고객사 예산 한도 (null=무제한)")
    budget_remaining: float | None = Field(
        None,
        description="고객사 잔여 예산 (null=무제한이거나 한도 미설정)",
    )
    budget_duration: str | None = Field(
        None,
        description="예산 초기화 주기 (예: '1d', '7d', '30d')",
    )
    tpm_limit: int | None = None
    rpm_limit: int | None = None
    keys: list[KeyUsageSummary] = Field(
        default_factory=list,
        description="키별 사용량 내역",
    )
