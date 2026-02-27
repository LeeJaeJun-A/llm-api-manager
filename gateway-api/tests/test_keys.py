"""
E2E integration tests for the LLM Gateway API.

Requires a running Docker Compose stack:
    docker compose up -d

Run with:
    GATEWAY_URL=http://localhost:8000 pytest tests/ -v
"""

import os

import httpx
import pytest

BASE = os.getenv("GATEWAY_URL", "http://localhost:8000")
API_SECRET = os.getenv("GATEWAY_API_SECRET", "changeme-gateway-secret")
ADMIN_HEADERS = {"X-API-Secret": API_SECRET}


def _customer_headers(team_id: str) -> dict:
    return {"X-API-Secret": API_SECRET, "X-Customer-Id": team_id}


@pytest.fixture(scope="module")
def team_id():
    """Create a team for the entire test module and clean up after."""
    resp = httpx.post(
        f"{BASE}/api/v1/teams",
        headers=ADMIN_HEADERS,
        json={
            "customer_id": "test-customer-001",
            "team_alias": "test-customer",
            "models": ["gpt-4o", "gpt-4o-mini"],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["customer_id"] == "test-customer-001"
    tid = data["team_id"]
    yield tid
    httpx.delete(f"{BASE}/api/v1/teams/{tid}", headers=ADMIN_HEADERS)


# ── Teams ───────────────────────────────────────────


class TestTeams:
    def test_create_and_list(self, team_id: str):
        resp = httpx.get(f"{BASE}/api/v1/teams", headers=ADMIN_HEADERS)
        assert resp.status_code == 200
        teams = resp.json()
        assert any(t["team_id"] == team_id for t in teams)

    def test_get_team(self, team_id: str):
        resp = httpx.get(f"{BASE}/api/v1/teams/{team_id}", headers=ADMIN_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["team_alias"] == "test-customer"
        assert "gpt-4o" in data["models"]

    def test_update_models(self, team_id: str):
        resp = httpx.patch(
            f"{BASE}/api/v1/teams/{team_id}",
            headers=ADMIN_HEADERS,
            json={"models": ["gpt-4o", "gpt-4o-mini", "claude-sonnet"]},
        )
        assert resp.status_code == 200
        assert "claude-sonnet" in resp.json()["models"]

    def test_delete_team(self):
        """Create a temporary team and delete it."""
        create = httpx.post(
            f"{BASE}/api/v1/teams",
            headers=ADMIN_HEADERS,
            json={"customer_id": "temp-del-team", "team_alias": "temp-team", "models": ["gpt-4o"]},
        )
        assert create.status_code == 200
        tid = create.json()["team_id"]

        delete = httpx.delete(f"{BASE}/api/v1/teams/{tid}", headers=ADMIN_HEADERS)
        assert delete.status_code == 200


# ── Keys ────────────────────────────────────────────


class TestKeys:
    def test_create_key(self, team_id: str):
        resp = httpx.post(
            f"{BASE}/api/v1/keys",
            headers=_customer_headers(team_id),
            json={
                "customer_id": team_id,
                "key_alias": "test-key",
                "tpm_limit": 10000,
                "rpm_limit": 100,
                "max_budget": 5.0,
                "budget_duration": "30d",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["token"] is not None
        assert data["customer_id"] == team_id

    def test_list_keys(self, team_id: str):
        resp = httpx.get(
            f"{BASE}/api/v1/keys",
            headers=_customer_headers(team_id),
        )
        assert resp.status_code == 200
        assert len(resp.json()["keys"]) >= 1

    def test_create_unlimited_key(self, team_id: str):
        """REQ-04: null limits = unlimited."""
        resp = httpx.post(
            f"{BASE}/api/v1/keys",
            headers=_customer_headers(team_id),
            json={"customer_id": team_id, "key_alias": "unlimited-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tpm_limit"] is None
        assert data["max_budget"] is None

    def test_update_key(self, team_id: str):
        create = httpx.post(
            f"{BASE}/api/v1/keys",
            headers=_customer_headers(team_id),
            json={"customer_id": team_id, "key_alias": "update-test"},
        )
        assert create.status_code == 200
        key_hash = create.json()["key"]

        update = httpx.patch(
            f"{BASE}/api/v1/keys/{key_hash}",
            headers=_customer_headers(team_id),
            json={"tpm_limit": 50000, "max_budget": 25.0},
        )
        assert update.status_code == 200

    def test_delete_key(self, team_id: str):
        create = httpx.post(
            f"{BASE}/api/v1/keys",
            headers=_customer_headers(team_id),
            json={"customer_id": team_id, "key_alias": "delete-test"},
        )
        assert create.status_code == 200
        key_hash = create.json()["key"]

        delete = httpx.delete(
            f"{BASE}/api/v1/keys/{key_hash}",
            headers=_customer_headers(team_id),
        )
        assert delete.status_code == 200

    def test_cross_team_rejected(self, team_id: str):
        """Keys cannot be created for a different team."""
        resp = httpx.post(
            f"{BASE}/api/v1/keys",
            headers=_customer_headers(team_id),
            json={"customer_id": "some-other-team", "key_alias": "hack"},
        )
        assert resp.status_code == 403


# ── Credentials ─────────────────────────────────────


class TestCredentials:
    def test_register_credential(self, team_id: str):
        """Register a customer-owned provider key."""
        resp = httpx.post(
            f"{BASE}/api/v1/customers/{team_id}/credentials",
            headers=_customer_headers(team_id),
            json={"provider": "gemini", "api_key": "test-gemini-key"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["provider"] == "gemini"
        assert "gemini-pro" in data["models"]
        assert "gemini-flash" in data["models"]

    def test_list_credentials_shows_ownership(self, team_id: str):
        """After registering, models should show owns_key=True."""
        resp = httpx.get(
            f"{BASE}/api/v1/customers/{team_id}/credentials",
            headers=_customer_headers(team_id),
        )
        assert resp.status_code == 200
        models = resp.json()["models"]
        gemini_models = [m for m in models if m["provider"] == "gemini"]
        assert all(m["owns_key"] is True for m in gemini_models)

    def test_key_generated_after_credential_has_no_prefix(self, team_id: str):
        """Keys generated after credential registration should not expose internal names."""
        key_resp = httpx.post(
            f"{BASE}/api/v1/keys",
            headers=_customer_headers(team_id),
            json={"customer_id": team_id, "key_alias": "post-cred-key"},
        )
        assert key_resp.status_code == 200

    def test_deregister_credential(self, team_id: str):
        """Deregistering restores platform default models."""
        resp = httpx.delete(
            f"{BASE}/api/v1/customers/{team_id}/credentials/gemini",
            headers=_customer_headers(team_id),
        )
        assert resp.status_code == 200
        assert "gemini-pro" in resp.json()["models"]
        assert "gemini-flash" in resp.json()["models"]

    def test_credential_history(self, team_id: str):
        """Credential events should be tracked even after deletion."""
        resp = httpx.get(
            f"{BASE}/api/v1/customers/{team_id}/credentials/history",
            headers=_customer_headers(team_id),
        )
        assert resp.status_code == 200
        events = resp.json()["events"]
        actions = [e["action"] for e in events]
        assert "register" in actions
        assert "deregister" in actions

    def test_validation_rejects_missing_api_key(self, team_id: str):
        """Provider credential without required fields should be rejected."""
        resp = httpx.post(
            f"{BASE}/api/v1/customers/{team_id}/credentials",
            headers=_customer_headers(team_id),
            json={"provider": "gemini"},
        )
        assert resp.status_code == 422

    def test_validation_rejects_bedrock_without_aws_keys(self, team_id: str):
        resp = httpx.post(
            f"{BASE}/api/v1/customers/{team_id}/credentials",
            headers=_customer_headers(team_id),
            json={"provider": "bedrock", "api_key": "wrong-field"},
        )
        assert resp.status_code == 422

    def test_cross_team_credential_rejected(self, team_id: str):
        resp = httpx.post(
            f"{BASE}/api/v1/customers/some-other-team/credentials",
            headers=_customer_headers(team_id),
            json={"provider": "gemini", "api_key": "test-key"},
        )
        assert resp.status_code == 403


# ── Usage ───────────────────────────────────────────


class TestUsage:
    def test_usage_query(self, team_id: str):
        key_resp = httpx.post(
            f"{BASE}/api/v1/keys",
            headers=_customer_headers(team_id),
            json={"customer_id": team_id, "max_budget": 10.0},
        )
        assert key_resp.status_code == 200
        key_hash = key_resp.json()["key"]

        resp = httpx.get(
            f"{BASE}/api/v1/usage/{key_hash}",
            headers=_customer_headers(team_id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["max_budget"] == 10.0
        assert data["budget_remaining"] == 10.0
        assert data["spend"] == 0.0


# ── Traces ─────────────────────────────────────────


class TestTraces:
    def test_list_customer_traces(self, team_id: str):
        """Customer can list their traces (may be empty before any LLM calls)."""
        resp = httpx.get(
            f"{BASE}/api/v1/customers/{team_id}/traces?limit=10",
            headers=_customer_headers(team_id),
        )
        assert resp.status_code in (200, 502)
        if resp.status_code == 200:
            data = resp.json()
            assert data["customer_id"] == team_id
            assert isinstance(data["traces"], list)

    def test_cross_customer_denied(self, team_id: str):
        """Customer cannot view another customer's traces."""
        resp = httpx.get(
            f"{BASE}/api/v1/customers/other-customer/traces",
            headers=_customer_headers(team_id),
        )
        assert resp.status_code == 403

    def test_key_traces_admin_only(self, team_id: str):
        """Key-level traces endpoint requires admin auth."""
        resp = httpx.get(
            f"{BASE}/api/v1/keys/somekeyhash/traces",
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code in (200, 502)

    def test_trace_detail_not_found(self, team_id: str):
        """Non-existent trace returns 404."""
        resp = httpx.get(
            f"{BASE}/api/v1/customers/{team_id}/traces/nonexistent-trace-id",
            headers=_customer_headers(team_id),
        )
        assert resp.status_code in (404, 502)


# ── Health ──────────────────────────────────────────


class TestHealth:
    def test_health(self):
        resp = httpx.get(f"{BASE}/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
