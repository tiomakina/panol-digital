"""Router principal — agrupa todos los endpoints de la API v1."""
from fastapi import APIRouter
from app.api.v1 import auth, brand, dashboard, loans, tools

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(tools.router)
api_router.include_router(loans.router)
api_router.include_router(dashboard.router)
api_router.include_router(brand.router)

# Los demás routers se agregarán aquí:
# api_router.include_router(users.router)
