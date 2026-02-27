from pydantic import BaseModel, Field


class KeyCreateRequest(BaseModel):
    customer_id: str = Field(..., description="고객사 ID")
    key_alias: str | None = Field(None, description="키 별칭")
    models: list[str] | None = Field(
        None,
        description="이 키에 허용할 모델 (미지정 시 team 모델 상속)",
    )
    tpm_limit: int | None = Field(None, description="TPM 한도 (null=무제한)")
    rpm_limit: int | None = Field(None, description="RPM 한도 (null=무제한)")
    max_budget: float | None = Field(None, description="예산 한도 USD (null=무제한)")
    budget_duration: str | None = Field(
        None,
        description="예산 초기화 주기 (예: '1d', '7d', '30d', null=초기화 없음)",
    )
    duration: str | None = Field(None, description="키 만료 기간 (예: '30d', '1h')")
    metadata: dict | None = Field(None, description="추가 메타데이터")


class KeyUpdateRequest(BaseModel):
    key_alias: str | None = None
    models: list[str] | None = None
    tpm_limit: int | None = None
    rpm_limit: int | None = None
    max_budget: float | None = None
    budget_duration: str | None = None
    duration: str | None = None
    metadata: dict | None = None


class KeyResponse(BaseModel):
    token: str | None = Field(None, description="발급된 API 키 (sk-xxx)")
    key: str | None = Field(None, description="키 해시 (조회용 ID)")
    key_alias: str | None = None
    key_name: str | None = None
    customer_id: str | None = Field(None, description="고객사 ID")
    models: list[str] = []
    tpm_limit: int | None = None
    rpm_limit: int | None = None
    max_budget: float | None = None
    budget_duration: str | None = None
    spend: float = 0.0
    expires: str | None = None
    metadata: dict | None = None


class KeyListResponse(BaseModel):
    keys: list[KeyResponse] = []
