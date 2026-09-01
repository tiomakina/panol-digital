"""Tareas Celery relacionadas a préstamos — marca vencidos y avisa a los responsables."""
import asyncio
from datetime import date

from sqlalchemy import select

from app.celery_app import celery_app
from app.core.database import AsyncSessionLocal, engine
from app.models.loan import Loan, LoanStatus
from app.services.notification_service import notify_overdue_loan


async def _mark_overdue_loans() -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Loan).where(Loan.status == LoanStatus.activo, Loan.due_date < date.today())
        )
        overdue = result.scalars().all()
        for loan in overdue:
            loan.status = LoanStatus.vencido
            # loan.tool/loan.borrower ya vienen cargados (lazy="joined" en el
            # modelo), así que esto no dispara queries extra.
            if not loan.alert_sent:
                await notify_overdue_loan(loan, loan.tool, loan.borrower)
                loan.alert_sent = True
        await db.commit()
        count = len(overdue)

    # Cada invocación de este task corre en un event loop propio (asyncio.run
    # más abajo), pero el engine/pool de conexiones es un singleton reutilizado
    # entre invocaciones dentro del mismo worker. Sin este dispose(), la
    # próxima corrida falla con "Future attached to a different loop" al
    # intentar usar una conexión asyncpg abierta en un loop ya cerrado.
    await engine.dispose()
    return count


@celery_app.task(name="app.tasks.loan_tasks.mark_overdue_loans")
def mark_overdue_loans() -> int:
    """
    Recorre los préstamos activos con fecha de devolución vencida, los marca
    como "vencido" y avisa al responsable por email/WhatsApp (si esos canales
    están configurados). Se ejecuta cada hora vía Celery beat (celery_app.py).
    """
    return asyncio.run(_mark_overdue_loans())
