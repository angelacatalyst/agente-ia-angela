"""
Finance Operations AI Manager — FastAPI Application Entry Point.

Architecture: FastAPI + LangGraph Multi-Agent + Anthropic Claude
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.agents.orchestrator import FinanceOrchestrator
from app.api.v1.endpoints.chat import set_orchestrator
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.models.database import Base, engine
from app.models.schemas import HealthResponse

configure_logging()
logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — startup and shutdown."""
    logger.info(
        "Starting Finance Ops AI Manager",
        version=settings.app_version,
        env=settings.app_env,
        model=settings.anthropic_model,
    )

    # Create database tables
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables ready")
    except Exception as exc:
        logger.warning("Database init failed (non-fatal in dev)", error=str(exc))

    # Initialize orchestrator
    orchestrator = FinanceOrchestrator()
    set_orchestrator(orchestrator)
    logger.info("LangGraph orchestrator initialized with 8 specialist agents")

    yield

    # Shutdown
    await engine.dispose()
    logger.info("Finance Ops AI Manager shutdown complete")


# ── FastAPI App ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Finance Operations AI Manager",
    description=(
        "AI-powered accounting operations platform for Nonprofit & For-Profit organizations. "
        "Powered by Anthropic Claude + LangGraph multi-agent architecture."
    ),
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


# ── Global exception handler ──────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health() -> HealthResponse:
    """Health check endpoint for load balancers and monitoring."""
    import redis.asyncio as aioredis

    services: dict[str, str] = {}

    # Check Redis
    try:
        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
        services["redis"] = "ok"
    except Exception:
        services["redis"] = "unavailable"

    # Check DB
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        services["database"] = "ok"
    except Exception:
        services["database"] = "unavailable"

    services["anthropic"] = "configured" if settings.anthropic_api_key else "missing"

    return HealthResponse(
        status="ok",
        version=settings.app_version,
        environment=settings.app_env,
        services=services,
    )


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(api_router)


# ── QBO OAuth shortcut: /callback → handler ──────────────────────────────────

from fastapi import Query as _Query
from fastapi.responses import RedirectResponse as _RedirectResponse

@app.get("/callback", tags=["Integrations"], include_in_schema=False)
async def qbo_callback_shortcut(
    code: str = _Query(None),
    realm_id: str = _Query(None),
    state: str = _Query(None),
    error: str = _Query(None),
):
    """Short redirect URI for Intuit OAuth (https://127.0.0.1.nip.io:8888/callback)."""
    if error:
        return {"error": error}
    from app.integrations.quickbooks.auth import exchange_code_for_tokens
    from app.models.database import QBOToken, AsyncSessionLocal
    from datetime import datetime, timezone

    try:
        token_data = await exchange_code_for_tokens(code, realm_id)
    except Exception as exc:
        return {"error": f"Token exchange failed: {exc}"}

    async with AsyncSessionLocal() as db:
        existing = await db.get(QBOToken, realm_id)
        if existing:
            existing.access_token = token_data["access_token"]
            existing.refresh_token = token_data["refresh_token"]
            existing.expires_at = token_data["expires_at"]
            existing.updated_at = datetime.now(timezone.utc)
        else:
            db.add(QBOToken(
                realm_id=realm_id,
                user_id="angela",
                access_token=token_data["access_token"],
                refresh_token=token_data["refresh_token"],
                expires_at=token_data["expires_at"],
            ))
        await db.commit()
    return {"status": "Empresa conectada exitosamente", "realm_id": realm_id}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=not settings.is_production,
        log_config=None,  # Use structlog instead
    )
