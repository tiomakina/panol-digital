"""
API de Dashboard — indicadores clave (KPIs) en tiempo real para la pantalla principal.
Endpoint: /api/v1/dashboard/
"""
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.loan import Loan, LoanStatus
from app.models.tool import Tool, ToolStatus
from app.models.user import User
from app.services.depreciation import calculate_current_value

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/kpis")
async def get_kpis(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Calcula los KPIs que alimentan las tarjetas del dashboard principal."""
    total_tools = (await db.execute(select(func.count(Tool.id)))).scalar_one()

    active_loans = (
        await db.execute(select(func.count(Loan.id)).where(Loan.status.in_([LoanStatus.activo, LoanStatus.vencido])))
    ).scalar_one()

    # "Vencido" incluye tanto los que Celery ya procesó (status=vencido) como
    # los que siguen en "activo" pero ya pasaron su fecha (aún no pasó la
    # corrida horaria de mark_overdue_loans) — si solo mirábamos "activo",
    # un préstamo dejaba de contar como vencido apenas Celery lo marcaba,
    # que es exactamente lo contrario de lo que debería mostrar el KPI.
    overdue_loans = (
        await db.execute(
            select(func.count(Loan.id)).where(
                (Loan.status == LoanStatus.vencido)
                | ((Loan.status == LoanStatus.activo) & (Loan.due_date < date.today()))
            )
        )
    ).scalar_one()

    maintenance_count = (
        await db.execute(select(func.count(Tool.id)).where(Tool.status == ToolStatus.mantenimiento))
    ).scalar_one()

    tools = (await db.execute(select(Tool))).scalars().all()
    inventory_value = sum((calculate_current_value(t) or 0) for t in tools)

    return {
        "total_tools": total_tools,
        "active_loans": active_loans,
        "overdue_loans": overdue_loans,
        "inventory_value": float(inventory_value),
        "maintenance_count": maintenance_count,
    }
