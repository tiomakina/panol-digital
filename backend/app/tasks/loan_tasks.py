"""
Tareas Celery relacionadas a préstamos:
  • mark_overdue_loans  — cada hora: marca vencidos y avisa al responsable
  • send_loan_reminders — cada día a las 08:00 UTC: avisa 1 día antes del vencimiento
"""
import asyncio
from datetime import date, timedelta

from sqlalchemy import select

from app.celery_app import celery_app
from app.core.database import AsyncSessionLocal, engine
from app.models.loan import Loan, LoanStatus
from app.services.notification_service import notify_overdue_loan, send_email, send_whatsapp


# ── Helpers compartidos ───────────────────────────────────────────────────────

async def _dispose():
    """
    Cada task corre en un event loop propio (asyncio.run). El engine/pool de
    conexiones es un singleton reutilizado entre invocaciones del mismo worker.
    Sin dispose() la siguiente corrida falla con "Future attached to a different
    loop" al intentar usar una conexión asyncpg abierta en un loop ya cerrado.
    """
    await engine.dispose()


# ── Task 1: marcar vencidos ───────────────────────────────────────────────────

async def _mark_overdue_loans() -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Loan).where(Loan.status == LoanStatus.activo, Loan.due_date < date.today())
        )
        overdue = result.scalars().all()
        for loan in overdue:
            loan.status = LoanStatus.vencido
            # loan.tool/loan.borrower vienen cargados (lazy="joined") sin query extra.
            if not loan.alert_sent:
                await notify_overdue_loan(loan, loan.tool, loan.borrower)
                loan.alert_sent = True
        await db.commit()
        count = len(overdue)
    await _dispose()
    return count


@celery_app.task(name="app.tasks.loan_tasks.mark_overdue_loans")
def mark_overdue_loans() -> int:
    """
    Marca como "vencido" todo préstamo activo con due_date < hoy y avisa al
    responsable por email/WhatsApp. Se ejecuta cada hora en punto.
    """
    return asyncio.run(_mark_overdue_loans())


# ── Task 2: recordatorio antes de vencer ─────────────────────────────────────

async def _send_loan_reminders() -> int:
    """
    Busca préstamos activos que vencen mañana y todavía no recibieron
    recordatorio (reminder_sent=False) y les avisa. Esto es distinto al aviso
    de vencido: acá la herramienta aún no se venció, es solo una advertencia
    para que el responsable recuerde devolver a tiempo.
    """
    tomorrow = date.today() + timedelta(days=1)
    sent = 0
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Loan).where(
                Loan.status == LoanStatus.activo,
                Loan.due_date == tomorrow,
                Loan.reminder_sent == False,  # noqa: E712
            )
        )
        loans = result.scalars().all()
        for loan in loans:
            tool = loan.tool
            borrower = loan.borrower
            if not borrower:
                continue
            subject = f"Recordatorio: mañana vence el préstamo de {tool.name}"
            body = (
                f"Hola {borrower.full_name},\n\n"
                f'Mañana ({tomorrow.strftime("%d/%m/%Y")}) vence el préstamo de '
                f'"{tool.name}". Por favor devuélvela al pañol antes del final del día.\n\n'
                f"Ante cualquier consulta, contacta al encargado.\n\n"
                f"— Pañol 360"
            )
            email_ok = await send_email(borrower.email, subject, body)
            wa_ok = False
            if getattr(borrower, "phone", None):
                wa_ok = await send_whatsapp(borrower.phone, body)
            if email_ok or wa_ok:
                loan.reminder_sent = True
                sent += 1
        await db.commit()
    await _dispose()
    return sent


@celery_app.task(name="app.tasks.loan_tasks.send_loan_reminders")
def send_loan_reminders() -> int:
    """
    Avisa a cada responsable de un préstamo que vence mañana. Corre una vez
    por día a las 08:00 UTC (11:00 Chile hora de verano). Solo notifica si
    el canal de email o WhatsApp está configurado; si no lo está, no hace nada.
    """
    return asyncio.run(_send_loan_reminders())
