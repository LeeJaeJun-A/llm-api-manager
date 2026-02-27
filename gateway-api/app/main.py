import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.dependencies import close_litellm_client, init_litellm_client
from app.routers import customers, keys, usage, credentials, traces
from app.services import audit

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_litellm_client()
    traces.init_langfuse_client()
    await audit.init_pool()
    logger.info("Gateway API started")
    yield
    await traces.close_langfuse_client()
    await close_litellm_client()
    await audit.close_pool()
    logger.info("Gateway API stopped")


app = FastAPI(
    title="LLM Gateway API",
    description="Self-service portal for LLM API key and usage management",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(customers.router)
app.include_router(keys.router)
app.include_router(usage.router)
app.include_router(credentials.router)
app.include_router(traces.router)


@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}
