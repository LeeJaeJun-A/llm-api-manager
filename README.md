# LLM API Gateway

LiteLLM Proxy + Langfuse 기반 LLM API 게이트웨이.
고객사별 가상 API 키를 발급하고, 사용량/한도를 관리하며, 모든 요청을 트레이스합니다.

## 아키텍처

```
고객사 앱  ──(sk-xxx)──►  LiteLLM Proxy (:4000)  ──►  OpenAI / Bedrock
                              │
셀프서비스 ──►  Gateway API (:8000)  ──(Admin API)──┘
                              │
                         PostgreSQL (:5432)
                              │
                         Langfuse (:3000)   ← 트레이스 자동 수집
```

## 빠른 시작

### 1. 환경 변수 설정

```bash
cp .env.example .env
# .env 파일을 열어 실제 값 입력
```

### 2. 실행

```bash
docker compose up -d
```

| 서비스 | URL | 설명 |
|---|---|---|
| LiteLLM Proxy | http://localhost:4000 | LLM 프록시 (고객사 앱이 직접 호출) |
| Gateway API | http://localhost:8000 | 셀프서비스 키 관리 API |
| Langfuse | http://localhost:3000 | 트레이스 모니터링 대시보드 |
| PostgreSQL | localhost:5432 | 사용량 + 트레이스 영구 저장 |
| Redis | localhost:6379 | Rate limiting |

### 3. Langfuse 초기 설정

1. http://localhost:3000 접속 후 계정 생성
2. Project 생성 → Settings → API Keys에서 Public/Secret Key 복사
3. `.env` 파일에 `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` 입력
4. `docker compose restart litellm-proxy`

## API 사용법

### 고객사(Customer) 등록 (관리자)

```bash
# 고객사 생성 — customer_id를 원하는 값으로 직접 지정
curl -X POST http://localhost:8000/api/v1/customers \
  -H "X-API-Secret: $GATEWAY_API_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "acme-corp",
    "customer_alias": "고객사A",
    "models": ["gpt-4o", "gpt-4o-mini"]
  }'
```

### 키 발급 (고객사 셀프서비스)

```bash
curl -X POST http://localhost:8000/api/v1/keys \
  -H "X-API-Secret: $GATEWAY_API_SECRET" \
  -H "X-Customer-Id: acme-corp" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "acme-corp",
    "key_alias": "production-key",
    "tpm_limit": 100000,
    "rpm_limit": 500,
    "max_budget": 100.0,
    "budget_duration": "30d"
  }'
```

무제한으로 설정하려면 `tpm_limit`, `rpm_limit`, `max_budget` 필드를 생략합니다.

### LLM 호출 (고객사 앱)

발급받은 키(`sk-xxx`)로 LiteLLM Proxy에 직접 호출합니다. OpenAI 호환 API입니다.

```bash
curl -X POST http://localhost:4000/chat/completions \
  -H "Authorization: Bearer sk-xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

### 사용량 조회

```bash
# 고객사 전체 사용량 (총 사용액, 한도, 잔액 + 키별 내역)
curl http://localhost:8000/api/v1/customers/<customer_id>/usage \
  -H "X-API-Secret: $GATEWAY_API_SECRET" \
  -H "X-Customer-Id: <customer_id>"

# 개별 키 사용량
curl http://localhost:8000/api/v1/usage/<key_hash> \
  -H "X-API-Secret: $GATEWAY_API_SECRET" \
  -H "X-Customer-Id: <customer_id>"
```

응답 예시 (`GET /customers/{id}/usage`):

```json
{
  "customer_id": "acme-corp",
  "customer_alias": "고객사A",
  "total_spend": 12.34,
  "max_budget": 100.0,
  "budget_remaining": 87.66,
  "budget_duration": "30d",
  "tpm_limit": 100000,
  "rpm_limit": 500,
  "keys": [
    {
      "key": "sk-...",
      "key_alias": "production-key",
      "spend": 10.00,
      "max_budget": 50.0,
      "budget_remaining": 40.0,
      "models": ["gpt-4o", "gpt-4o-mini"]
    }
  ]
}
```

### 트레이스 (Langfuse)

LLM 호출 이력은 Langfuse 대시보드(http://localhost:3000)에서 직접 조회합니다.

커스텀 콜백(`litellm/custom_callbacks.py`)이 모든 LLM 호출에 대해 자동으로
customer_id(team_id)를 Langfuse trace의 `userId`로 주입합니다.
따라서 Langfuse의 **Users** 뷰에서 고객사별 사용량과 비용을 바로 확인할 수 있습니다.

## 등록된 모델 (플랫폼 기본)

| 분류 | 모델명 | Provider |
|---|---|---|
| 사고 (Reasoning) | `gpt-4o` | OpenAI |
| 사고 (Reasoning) | `claude-sonnet` | Anthropic |
| 사고 (Reasoning) | `gemini-pro` | Google Gemini |
| 사고 (Reasoning) | `bedrock-claude-sonnet` | AWS Bedrock |
| 일반 (General) | `gpt-4o-mini` | OpenAI |
| 일반 (General) | `claude-haiku` | Anthropic |
| 일반 (General) | `gemini-flash` | Google Gemini |
| 일반 (General) | `bedrock-claude-haiku` | AWS Bedrock |

API 키가 설정된 provider만 자동으로 등록됩니다 (`.env`에서 빈 값은 스킵).
모델 추가/변경은 `litellm/config.yaml`을 수정합니다. 부팅 시 자동으로 키가 있는 모델만 필터링됩니다.

### 고객사 자체 Provider 키 등록

고객사가 특정 provider의 API 키를 직접 보유한 경우, 해당 키를 등록할 수 있습니다.
등록하지 않은 provider는 플랫폼 기본 키로 동작합니다.
**호출 시 모델명은 항상 동일합니다** (`gemini-pro`, `gpt-4o` 등).

```bash
# 1. 고객사가 자신의 Gemini 키 등록
curl -X POST http://localhost:8000/api/v1/customers/<customer_id>/credentials \
  -H "X-API-Secret: $GATEWAY_API_SECRET" \
  -H "X-Customer-Id: <customer_id>" \
  -H "Content-Type: application/json" \
  -d '{"provider": "gemini", "api_key": "customer-gemini-key"}'

# 2. 키 발급 (자동으로 aliases 설정됨 — 호출부 변화 없음)
curl -X POST http://localhost:8000/api/v1/keys \
  -H "X-API-Secret: $GATEWAY_API_SECRET" \
  -H "X-Customer-Id: <customer_id>" \
  -H "Content-Type: application/json" \
  -d '{"customer_id": "<customer_id>"}'

# 3. 고객사는 그대로 model="gemini-pro"로 호출
curl -X POST http://localhost:4000/chat/completions \
  -H "Authorization: Bearer sk-xxx" \
  -d '{"model": "gemini-pro", "messages": [...]}'
# → 내부적으로 고객사 자체 Gemini 키 사용
```

```bash
# 등록된 모델 + 키 소유 여부 조회
curl http://localhost:8000/api/v1/customers/<customer_id>/credentials \
  -H "X-API-Secret: $GATEWAY_API_SECRET" \
  -H "X-Customer-Id: <customer_id>"

# 자체 키 제거 (플랫폼 기본으로 자동 복원)
curl -X DELETE http://localhost:8000/api/v1/customers/<customer_id>/credentials/gemini \
  -H "X-API-Secret: $GATEWAY_API_SECRET" \
  -H "X-Customer-Id: <customer_id>"

# 자격증명 변경 이력 조회 (등록/삭제/교체 모든 이벤트)
curl http://localhost:8000/api/v1/customers/<customer_id>/credentials/history \
  -H "X-API-Secret: $GATEWAY_API_SECRET" \
  -H "X-Customer-Id: <customer_id>"
```

## 테스트

```bash
cd gateway-api
pip install httpx pytest
GATEWAY_URL=http://localhost:8000 pytest tests/ -v
```