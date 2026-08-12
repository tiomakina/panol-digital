"""
API de indicadores económicos de Chile (dólar, UF, euro, UTM) para el
header. Endpoint: /api/v1/indicators/
"""
from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.models.user import User
from app.services.economic_indicators_service import get_indicators

router = APIRouter(prefix="/indicators", tags=["Indicadores"])


@router.get("/economic")
async def economic_indicators(user: User = Depends(get_current_user)):
    return await get_indicators()
