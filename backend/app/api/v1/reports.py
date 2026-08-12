"""
API de Reportes — inventario valorizado, historial de préstamos y auditoría.
Endpoint: /api/v1/reports/
"""
import csv
import io
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.audit import AuditLog
from app.models.loan import Loan, LoanStatus
from app.models.tool import Tool
from app.models.user import User
from app.schemas.audit import AuditLogOut
from app.services.depreciation import calculate_current_value

router = APIRouter(prefix="/reports", tags=["Reportes"])


async def _inventory_rows(db: AsyncSession) -> list[dict]:
    tools = (await db.execute(select(Tool).order_by(Tool.category, Tool.name))).scalars().all()
    rows = []
    for tool in tools:
        current_value = calculate_current_value(tool)
        rows.append(
            {
                "id": tool.id,
                "name": tool.name,
                "brand": tool.brand,
                "category": tool.category,
                "status": tool.status.value,
                "purchase_date": tool.purchase_date.isoformat() if tool.purchase_date else None,
                "purchase_cost": float(tool.purchase_cost) if tool.purchase_cost is not None else None,
                "current_value": float(current_value) if current_value is not None else None,
            }
        )
    return rows


@router.get("/inventory")
async def inventory_report(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Inventario valorizado: costo de compra y valor en libros actual de cada herramienta."""
    rows = await _inventory_rows(db)
    total_cost = sum(r["purchase_cost"] or 0 for r in rows)
    total_current_value = sum(r["current_value"] or 0 for r in rows)
    return {"tools": rows, "total_purchase_cost": total_cost, "total_current_value": total_current_value}


@router.get("/inventory.csv")
async def inventory_report_csv(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Igual que /reports/inventory pero como CSV descargable."""
    rows = await _inventory_rows(db)

    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=["id", "name", "brand", "category", "status", "purchase_date", "purchase_cost", "current_value"],
    )
    writer.writeheader()
    writer.writerows(rows)
    buffer.seek(0)

    filename = f"inventario_{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/loans")
async def loans_report(
    status_filter: LoanStatus | None = Query(None, alias="status"),
    date_from: date | None = None,
    date_to: date | None = None,
    borrower_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Historial de préstamos, con filtros opcionales de estado, rango de fechas y responsable."""
    stmt = select(Loan)
    if status_filter:
        stmt = stmt.where(Loan.status == status_filter)
    if date_from:
        stmt = stmt.where(Loan.loan_date >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(Loan.loan_date <= datetime.combine(date_to, datetime.max.time()))
    if borrower_id:
        stmt = stmt.where(Loan.borrower_id == borrower_id)
    stmt = stmt.order_by(Loan.loan_date.desc())

    loans = (await db.execute(stmt)).scalars().all()
    return {
        "count": len(loans),
        "loans": [
            {
                "id": loan.id,
                "tool": loan.tool.name if loan.tool else None,
                "borrower": loan.borrower.full_name if loan.borrower else None,
                "loan_date": loan.loan_date.isoformat(),
                "due_date": loan.due_date.isoformat(),
                "return_date": loan.return_date.isoformat() if loan.return_date else None,
                "status": loan.status.value,
                "return_condition": loan.return_condition.value if loan.return_condition else None,
            }
            for loan in loans
        ],
    }


@router.get("/audit", response_model=list[AuditLogOut])
async def audit_report(
    entity_type: str | None = None,
    user_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("jefe")),
):
    """Registro de auditoría forense — solo visible para el Jefe."""
    stmt = select(AuditLog)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    stmt = stmt.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(stmt)
    return result.scalars().all()
