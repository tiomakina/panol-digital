"""
Servicio de Notificaciones — avisa por email y/o WhatsApp cuando corresponde
(hoy: préstamos vencidos, disparado desde app/tasks/loan_tasks.py).

Ambos canales son opcionales (así están documentados en .env.example): si
no están configurados, se omiten en silencio — nunca deben romper el flujo
de Celery ni el de la API.
"""
import logging

import aiosmtplib
import httpx
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger("panol.notifications")


def email_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD)


def whatsapp_configured() -> bool:
    return bool(settings.WHATSAPP_API_TOKEN and settings.WHATSAPP_PHONE_ID)


async def send_email(to: str, subject: str, body: str) -> bool:
    """Envía un email por SMTP. Devuelve False (sin excepción) si no está configurado o falla."""
    if not email_configured():
        logger.info("SMTP no configurado — se omite el email a %s (%s)", to, subject)
        return False
    try:
        message = EmailMessage()
        message["From"] = settings.SMTP_USER
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=True,
        )
        return True
    except Exception:
        logger.exception("Error enviando email a %s", to)
        return False


async def send_whatsapp(phone: str, message: str) -> bool:
    """
    Envía un mensaje por la API de WhatsApp Business Cloud (Meta).
    Devuelve False (sin excepción) si no está configurado o falla.
    """
    if not whatsapp_configured():
        logger.info("WhatsApp no configurado — se omite el mensaje a %s", phone)
        return False
    url = f"https://graph.facebook.com/v18.0/{settings.WHATSAPP_PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {settings.WHATSAPP_API_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": message},
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(url, json=payload, headers=headers)
            res.raise_for_status()
        return True
    except Exception:
        logger.exception("Error enviando WhatsApp a %s", phone)
        return False


async def notify_low_stock(tool_name: str, available: int, min_stock: int, recipients: list[str]) -> None:
    """Avisa a los Encargados/Jefes cuando el stock disponible baja del mínimo configurado."""
    subject = f"⚠ Stock mínimo alcanzado: {tool_name}"
    body = (
        f"Atención:\n\n"
        f'La herramienta "{tool_name}" tiene solo {available} unidad(es) disponible(s), '
        f"que está por debajo del mínimo configurado ({min_stock}).\n\n"
        f"Considera devolver o gestionar el reabastecimiento.\n\n"
        f"— Pañol 360"
    )
    for email in recipients:
        await send_email(email, subject, body)


async def notify_overdue_loan(loan, tool, borrower) -> None:
    """Avisa al responsable de un préstamo que acaba de marcarse como vencido."""
    subject = f"Préstamo vencido: {tool.name}"
    body = (
        f"Hola {borrower.full_name},\n\n"
        f'El préstamo de "{tool.name}" venció el {loan.due_date.strftime("%d/%m/%Y")}.\n'
        f"Por favor devolvé la herramienta al pañol a la brevedad.\n\n"
        f"Este es un aviso automático de Pañol."
    )
    await send_email(borrower.email, subject, body)
    if borrower.phone:
        await send_whatsapp(borrower.phone, body)
