"""
API de Préstamos — creación, devolución y generación de vales PDF con firma digital.
Endpoint: /api/v1/loans/
"""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.loan import Loan, LoanStatus, ReturnCondition
from app.models.maintenance import MaintenanceRecord, MaintenanceStatus
from app.models.tool import Tool, ToolStatus
from app.models.user import User
from app.schemas.loan import LoanCreate, LoanOut, LoanReturnInput
from app.services.pdf_service import VOUCHER_DIR, generate_loan_voucher

router = APIRouter(prefix="/loans", tags=["Préstamos"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/recent")
async def recent_loans_partial(request: Request, db: AsyncSession = Depends(get_db)):
    """Fragmento HTML (HTMX) con los préstamos activos más recientes, para el dashboard."""
    stmt = (
        select(Loan)
        .where(Loan.status.in_([LoanStatus.activo, LoanStatus.vencido]))
        .order_by(Loan.loan_date.desc())
        .limit(6)
    )
    result = await db.execute(stmt)
    loans = result.scalars().all()
    return templates.TemplateResponse(
        "components/loans_recent.html", {"request": request, "loans": loans, "today": date.today()}
    )


@router.get("", response_model=list[LoanOut])
async def list_loans(
    status_filter: LoanStatus | None = Query(None, alias="status"),
    tool_id: int | None = None,
    borrower_id: int | None = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Lista préstamos con filtros opcionales de estado, herramienta o responsable."""
    stmt = select(Loan)
    if status_filter:
        stmt = stmt.where(Loan.status == status_filter)
    if tool_id:
        stmt = stmt.where(Loan.tool_id == tool_id)
    if borrower_id:
        stmt = stmt.where(Loan.borrower_id == borrower_id)
    stmt = stmt.order_by(Loan.loan_date.desc()).offset(skip).limit(limit)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{loan_id}", response_model=LoanOut)
async def get_loan(loan_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    loan = await db.get(Loan, loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Préstamo no encontrado")
    return loan


@router.post("", response_model=LoanOut, status_code=status.HTTP_201_CREATED)
async def create_loan(
    payload: LoanCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("encargado")),
):
    """Registra un préstamo, marca la herramienta como prestada y genera el vale PDF."""
    tool = await db.get(Tool, payload.tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Herramienta no encontrada")
    if tool.status != ToolStatus.disponible:
        raise HTTPException(status_code=400, detail="La herramienta no está disponible para préstamo")

    borrower = await db.get(User, payload.borrower_id)
    if not borrower or not borrower.is_active:
        raise HTTPException(status_code=404, detail="Responsable no encontrado o inactivo")

    loan = Loan(
        tool_id=payload.tool_id,
        borrower_id=payload.borrower_id,
        issued_by_id=user.id,
        due_date=payload.due_date,
        purpose=payload.purpose,
        notes=payload.notes,
        signature_data=payload.signature_data,
    )
    tool.status = ToolStatus.prestado
    db.add(loan)
    await db.flush()  # asigna loan.id sin cerrar la transacción

    loan.voucher_pdf_url = generate_loan_voucher(loan, tool, borrower, user)

    await db.commit()
    await db.refresh(loan)
    return loan


@router.post("/{loan_id}/return", response_model=LoanOut)
async def return_loan(
    loan_id: int,
    payload: LoanReturnInput,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("encargado")),
):
    """Registra la devolución de una herramienta prestada."""
    loan = await db.get(Loan, loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Préstamo no encontrado")
    if loan.status not in (LoanStatus.activo, LoanStatus.vencido):
        raise HTTPException(status_code=400, detail="Este préstamo ya fue cerrado")

    tool = await db.get(Tool, loan.tool_id)

    loan.return_date = datetime.utcnow()
    loan.return_condition = payload.return_condition
    loan.status = LoanStatus.devuelto
    if payload.notes:
        loan.notes = payload.notes

    if tool:
        if payload.return_condition == ReturnCondition.bueno:
            tool.status = ToolStatus.disponible
        elif payload.return_condition == ReturnCondition.perdido:
            tool.status = ToolStatus.baja
            loan.status = LoanStatus.extraviado
        else:
            tool.status = ToolStatus.mantenimiento
            # Si no creamos el registro acá, la herramienta queda en
            # "mantenimiento" sin nada que lo explique en el módulo de
            # Mantenimiento — el motivo de la devolución (dañado/a reparar)
            # es justamente el motivo del envío.
            condition_label = "dañada" if payload.return_condition == ReturnCondition.dañado else "a reparación"
            reason = f"Devuelta {condition_label} tras el préstamo #{loan.id}."
            if payload.notes:
                reason += f" Observación: {payload.notes}"
            db.add(MaintenanceRecord(
                tool_id=tool.id,
                reason=reason,
                status=MaintenanceStatus.en_proceso,
                sent_date=date.today(),
                created_by_id=user.id,
            ))

    await db.commit()
    await db.refresh(loan)
    return loan


@router.get("/{loan_id}/voucher")
async def download_voucher(loan_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Descarga el vale PDF del préstamo (lo regenera si aún no existe)."""
    loan = await db.get(Loan, loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Préstamo no encontrado")

    tool = await db.get(Tool, loan.tool_id)
    borrower = await db.get(User, loan.borrower_id)
    issued_by = await db.get(User, loan.issued_by_id)
    if not tool or not borrower or not issued_by:
        raise HTTPException(status_code=404, detail="Datos del préstamo incompletos")

    voucher_url = generate_loan_voucher(loan, tool, borrower, issued_by)
    if loan.voucher_pdf_url != voucher_url:
        loan.voucher_pdf_url = voucher_url
        await db.commit()

    file_path = VOUCHER_DIR / f"vale_{loan.id}.pdf"
    return FileResponse(file_path, media_type="application/pdf", filename=f"vale_{loan.id}.pdf")
