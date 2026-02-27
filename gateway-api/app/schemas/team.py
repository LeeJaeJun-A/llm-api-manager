from pydantic import BaseModel, Field


class TeamCreateRequest(BaseModel):
    customer_id: str = Field(
        ...,
        description="고객사 ID (원하는 값으로 직접 지정, LiteLLM team_id로 사용)",
    )
    team_alias: str = Field(..., description="고객사 이름")
    models: list[str] = Field(
        ...,
        description="허용 모델 목록 (예: ['gpt-4o', 'gpt-4o-mini'])",
    )
    tpm_limit: int | None = Field(None, description="팀 전체 TPM 한도 (null=무제한)")
    rpm_limit: int | None = Field(None, description="팀 전체 RPM 한도 (null=무제한)")
    max_budget: float | None = Field(None, description="팀 전체 예산 한도 USD (null=무제한)")
    budget_duration: str | None = Field(
        None,
        description="예산 초기화 주기 (예: '1d', '7d', '30d', null=초기화 없음)",
    )
    metadata: dict | None = Field(None, description="추가 메타데이터")


class TeamUpdateRequest(BaseModel):
    models: list[str] | None = Field(None, description="허용 모델 목록 변경")
    tpm_limit: int | None = None
    rpm_limit: int | None = None
    max_budget: float | None = None
    budget_duration: str | None = None
    metadata: dict | None = None


class TeamResponse(BaseModel):
    customer_id: str = Field(..., description="고객사 ID")
    team_id: str = Field(..., description="LiteLLM 내부 team_id (= customer_id)")
    team_alias: str | None = None
    models: list[str] = []
    tpm_limit: int | None = None
    rpm_limit: int | None = None
    max_budget: float | None = None
    budget_duration: str | None = None
    spend: float = 0.0
    metadata: dict | None = None
