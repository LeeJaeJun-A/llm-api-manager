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
    id           BIGSERIAL PRIMARY KEY,
    customer_id  TEXT      NOT NULL,
    provider     TEXT      NOT NULL,
    action       TEXT      NOT NULL,
    detail       JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ce_customer ON credential_events (customer_id, created_at DESC);
"""


async def _migrate_team_to_customer(conn: asyncpg.Connection) -> None:
    """One-time: rename team_id to customer_id if present (existing DBs)."""
    rows = await conn.fetch(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'credential_events' AND column_name IN ('team_id', 'customer_id')
        """
    )
    names = {r["column_name"] for r in rows}
    if "team_id" in names and "customer_id" not in names:
        await conn.execute(
            "ALTER TABLE credential_events RENAME COLUMN team_id TO customer_id"
        )
        await conn.execute("DROP INDEX IF EXISTS idx_ce_team")
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ce_customer ON credential_events (customer_id, created_at DESC)"
        )
        logger.info("Audit table migrated: team_id -> customer_id")


async def init_pool() -> None:
    global _pool
    settings = get_settings()
    _pool = await asyncpg.create_pool(
        settings.database_url,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
    )
    async with _pool.acquire() as conn:
        await _migrate_team_to_customer(conn)  # before CREATE_TABLE so existing table gets customer_id
        await conn.execute(CREATE_TABLE)
    logger.info("Audit DB pool initialized")


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def log_event(
    customer_id: str,
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
            INSERT INTO credential_events (customer_id, provider, action, detail)
            VALUES ($1, $2, $3, $4::jsonb)
            """,
            customer_id,
            provider,
            action,
            _to_json(detail),
        )


async def get_history(
    customer_id: str,
    provider: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Retrieve credential event history for a customer."""
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        if provider:
            rows = await conn.fetch(
                """
                SELECT id, customer_id, provider, action, detail, created_at
                FROM credential_events
                WHERE customer_id = $1 AND provider = $2
                ORDER BY created_at DESC
                LIMIT $3
                """,
                customer_id,
                provider,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, customer_id, provider, action, detail, created_at
                FROM credential_events
                WHERE customer_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                customer_id,
                limit,
            )
    return [
        {
            "id": r["id"],
            "customer_id": r["customer_id"],
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
