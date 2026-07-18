"""API v1 router — aggregates all module endpoints."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    audit,
    chat,
    controller,
    eod,
    grants,
    integrations,
    payments,
    qbo_data,
    sops,
    transactions,
    vendors,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(chat.router)
api_router.include_router(audit.router)
api_router.include_router(transactions.router)
api_router.include_router(grants.router)
api_router.include_router(payments.router)
api_router.include_router(vendors.router)
api_router.include_router(sops.router)
api_router.include_router(eod.router)
api_router.include_router(controller.router)
api_router.include_router(integrations.router)
api_router.include_router(qbo_data.router)
