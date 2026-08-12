"""Router principal — agrupa todos los endpoints de la API v1."""
from fastapi import APIRouter
from app.api.v1 import (
    auth,
    backup,
    brand,
    dashboard,
    indicators,
    loans,
    lookups,
    maintenance,
    reports,
    toolbox_audits,
    toolboxes,
    tools,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(tools.router)
api_router.include_router(loans.router)
api_router.include_router(toolboxes.router)
api_router.include_router(reports.router)
api_router.include_router(users.router)
api_router.include_router(dashboard.router)
api_router.include_router(brand.router)
api_router.include_router(lookups.router)
api_router.include_router(maintenance.router)
api_router.include_router(toolbox_audits.router)
api_router.include_router(backup.router)
api_router.include_router(indicators.router)
