"""
Credential audit log backed by PostgreSQL.

Records every provider credential registration, deletion, and swap
so that history is preserved even after credentials are removed.
"""

import json
import logging

import asyncpg

from app.config import get_settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS credential_events (
    id          BIGSERIAL PRIMARY KEY,
    team_id     TEXT      NOT NULL,
    provider    TEXT      NOT NULL,
    action      TEXT      NOT NULL,
    detail      JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ce_team ON credential_events (team_id, created_at DESC);
"""


async def init_pool() -> None:
    global _pool
    settings = get_settings()
    _pool = await asyncpg.create_pool(
        settings.database_url,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
    )
    async with _pool.acquire() as conn:
        await conn.execute(CREATE_TABLE)
    logger.info("Audit DB pool initialized")


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def log_event(
    team_id: str,
    provider: str,
    action: str,
    detail: dict | None = None,
) -> None:
    """Append a credential event to the audit log."""
    if not _pool:
        return
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO credential_events (team_id, provider, action, detail)
            VALUES ($1, $2, $3, $4::jsonb)
            """,
            team_id,
            provider,
            action,
            _to_json(detail),
        )


async def get_history(
    team_id: str,
    provider: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Retrieve credential event history for a team."""
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        if provider:
            rows = await conn.fetch(
                """
                SELECT id, team_id, provider, action, detail, created_at
                FROM credential_events
                WHERE team_id = $1 AND provider = $2
                ORDER BY created_at DESC
                LIMIT $3
                """,
                team_id,
                provider,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, team_id, provider, action, detail, created_at
                FROM credential_events
                WHERE team_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                team_id,
                limit,
            )
    return [
        {
            "id": r["id"],
            "customer_id": r["team_id"],
            "provider": r["provider"],
            "action": r["action"],
            "detail": r["detail"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


def _to_json(obj: dict | None) -> str | None:
    if obj is None:
        return None
    return json.dumps(obj, default=str)
