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
from app.core.security import require_role
from app.models.audit import AuditLog
from app.models.loan import Loan, LoanStatus
from app.models.tool import Tool
from app.models.toolbox import Toolbox
from app.models.user import User
from app.schemas.audit import AuditLogOut
from app.services.depreciation import calculate_current_value

router = APIRouter(prefix="/reports", tags=["Reportes"])


_INVENTORY_CSV_COLUMNS = [
    "id", "name", "brand", "category", "serial_number", "location", "supplier",
    "status", "purchase_date", "purchase_cost", "current_value",
]


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
                "serial_number": tool.serial_number,
                "location": tool.location,
                "supplier": tool.supplier,
                "status": tool.status.value,
                "purchase_date": tool.purchase_date.isoformat() if tool.purchase_date else None,
                "purchase_cost": float(tool.purchase_cost) if tool.purchase_cost is not None else None,
                "current_value": float(current_value) if current_value is not None else None,
            }
        )
    return rows


def _inventory_summary(rows: list[dict]) -> list[dict]:
    """
    Agrupa por nombre de herramienta — como puede haber varias unidades del
    mismo modelo distinguidas solo por su número de serie, esto da la
    cantidad total de cada una; las filas de detalle (con serie + ubicación)
    son las que permiten ubicar cada unidad puntual.
    """
    groups: dict[str, dict] = {}
    for row in rows:
        key = row["name"]
        if key not in groups:
            groups[key] = {"name": row["name"], "category": row["category"], "quantity": 0}
        groups[key]["quantity"] += 1
    return sorted(groups.values(), key=lambda g: g["name"])


@router.get("/inventory")
async def inventory_report(db: AsyncSession = Depends(get_db), user: User = Depends(require_role("encargado"))):
    """Inventario valorizado: costo de compra y valor en libros actual de cada herramienta."""
    rows = await _inventory_rows(db)
    total_cost = sum(r["purchase_cost"] or 0 for r in rows)
    total_current_value = sum(r["current_value"] or 0 for r in rows)
    return {
        "tools": rows,
        "summary": _inventory_summary(rows),
        "total_purchase_cost": total_cost,
        "total_current_value": total_current_value,
    }


@router.get("/inventory.csv")
async def inventory_report_csv(db: AsyncSession = Depends(get_db), user: User = Depends(require_role("encargado"))):
    """Igual que /reports/inventory pero como CSV descargable."""
    rows = await _inventory_rows(db)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_INVENTORY_CSV_COLUMNS)
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
    user: User = Depends(require_role("encargado")),
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
    rows = [
        {
            "id": loan.id,
            "tool": loan.tool.name if loan.tool else None,
            "tool_brand": loan.tool.brand if loan.tool else None,
            "tool_category": loan.tool.category if loan.tool else None,
            "tool_serial_number": loan.tool.serial_number if loan.tool else None,
            "borrower": loan.borrower.full_name if loan.borrower else None,
            "loan_date": loan.loan_date.isoformat(),
            "due_date": loan.due_date.isoformat(),
            "return_date": loan.return_date.isoformat() if loan.return_date else None,
            "status": loan.status.value,
            "return_condition": loan.return_condition.value if loan.return_condition else None,
        }
        for loan in loans
    ]

    # Cantidad de préstamos por herramienta — útil cuando hay varias
    # unidades del mismo modelo (cada una con su propio número de serie)
    # para ver cuál se pide más.
    summary_groups: dict[str, dict] = {}
    for row in rows:
        key = row["tool"] or "—"
        if key not in summary_groups:
            summary_groups[key] = {"tool": key, "quantity": 0}
        summary_groups[key]["quantity"] += 1
    summary = sorted(summary_groups.values(), key=lambda g: g["tool"])

    return {"count": len(loans), "loans": rows, "summary": summary}


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
    logs = result.scalars().all()

    # La columna "Entidad" del reporte mostraba solo "user #1" (tipo + id),
    # sin nada legible — acá se resuelve un nombre para los tipos de
    # entidad que realmente se auditan (ver entity_type= en el código:
    # solo son "user", "tool" y "toolbox"; "backup" no tiene un id de fila
    # asociado). No es un JOIN porque AuditLog.entity_type/entity_id son
    # genéricos (un mismo log audita cualquier tabla), así que se resuelve
    # en un par de queries en batch en vez de una FK real.
    ids_by_type: dict[str, set[int]] = {"user": set(), "tool": set(), "toolbox": set()}
    for log in logs:
        if log.entity_type in ids_by_type and log.entity_id:
            ids_by_type[log.entity_type].add(log.entity_id)

    labels_by_type: dict[str, dict[int, str]] = {"user": {}, "tool": {}, "toolbox": {}}
    if ids_by_type["user"]:
        rows = (await db.execute(select(User).where(User.id.in_(ids_by_type["user"])))).scalars().all()
        labels_by_type["user"] = {u.id: u.full_name for u in rows}
    if ids_by_type["tool"]:
        rows = (await db.execute(select(Tool).where(Tool.id.in_(ids_by_type["tool"])))).scalars().all()
        labels_by_type["tool"] = {t.id: t.name for t in rows}
    if ids_by_type["toolbox"]:
        rows = (await db.execute(select(Toolbox).where(Toolbox.id.in_(ids_by_type["toolbox"])))).scalars().all()
        labels_by_type["toolbox"] = {tb.id: tb.name for tb in rows}

    for log in logs:
        log.entity_label = labels_by_type.get(log.entity_type, {}).get(log.entity_id)

    return logs
