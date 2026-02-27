from pydantic import BaseModel, Field


class CustomerCreateRequest(BaseModel):
    customer_id: str = Field(
        ...,
        description="고객사 ID (원하는 값으로 직접 지정, LiteLLM team_id로 사용)",
    )
    customer_alias: str = Field(..., description="고객사 이름")
    models: list[str] = Field(
        ...,
        description="허용 모델 목록 (예: ['gpt-4o', 'gpt-4o-mini'])",
    )
    tpm_limit: int | None = Field(None, description="고객사 전체 TPM 한도 (null=무제한)")
    rpm_limit: int | None = Field(None, description="고객사 전체 RPM 한도 (null=무제한)")
    max_budget: float | None = Field(None, description="고객사 전체 예산 한도 USD (null=무제한)")
    budget_duration: str | None = Field(
        None,
        description="예산 초기화 주기 (예: '1d', '7d', '30d', null=초기화 없음)",
    )
    metadata: dict | None = Field(None, description="추가 메타데이터")


class CustomerUpdateRequest(BaseModel):
    models: list[str] | None = Field(None, description="허용 모델 목록 변경")
    tpm_limit: int | None = None
    rpm_limit: int | None = None
    max_budget: float | None = None
    budget_duration: str | None = None
    metadata: dict | None = None


class CustomerResponse(BaseModel):
    customer_id: str = Field(..., description="고객사 ID")
    customer_alias: str | None = None
    models: list[str] = []
    tpm_limit: int | None = None
    rpm_limit: int | None = None
    max_budget: float | None = None
    budget_duration: str | None = None
    spend: float = 0.0
    metadata: dict | None = None
