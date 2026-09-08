"""
Servicio de Notificaciones — avisa por email y/o WhatsApp cuando corresponde
(hoy: préstamos vencidos, disparado desde app/tasks/loan_tasks.py).

Ambos canales son opcionales (así están documentados en .env.example): si
no están configurados, se omiten en silencio — nunca deben romper el flujo
de Celery ni el de la API.

La configuración por tenant (email_enabled, whatsapp_enabled) se lee desde
notification_config.py — cada empresa puede activar/desactivar canales desde
la pantalla de Notificaciones en Administración.
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


def _notification_enabled(channel: str) -> bool:
    """
    Verifica si el canal está activo en la configuración del tenant.
    Falla en silencio: si no se puede leer la config, el canal se considera activo.
    """
    try:
        from app.core.notification_config import load_notification_config
        cfg = load_notification_config()
        if channel == "email":
            return bool(cfg.get("email_enabled", True))
        elif channel == "whatsapp":
            return bool(cfg.get("whatsapp_enabled", False))
    except Exception:
        pass
    return True


async def send_email(to: str, subject: str, body: str, log_event: str = "general") -> bool:
    """Envía un email por SMTP. Devuelve False (sin excepción) si no está configurado o falla."""
    if not email_configured():
        logger.info("SMTP no configurado — se omite el email a %s (%s)", to, subject)
        return False
    if not _notification_enabled("email"):
        logger.info("Email desactivado en config del tenant — se omite email a %s (%s)", to, subject)
        return False
    try:
        message = EmailMessage()
        message["From"] = settings.SMTP_FROM or settings.SMTP_USER
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
        _log_notification(channel="email", to=to, subject=subject, ok=True, event_type=log_event)
        return True
    except Exception:
        logger.exception("Error enviando email a %s", to)
        _log_notification(channel="email", to=to, subject=subject, ok=False, event_type=log_event)
        return False


async def send_whatsapp(phone: str, message: str, log_event: str = "general") -> bool:
    """
    Envía un mensaje por la API de WhatsApp Business Cloud (Meta).
    Devuelve False (sin excepción) si no está configurado o falla.
    """
    if not whatsapp_configured():
        logger.info("WhatsApp no configurado — se omite el mensaje a %s", phone)
        return False
    if not _notification_enabled("whatsapp"):
        logger.info("WhatsApp desactivado en config del tenant — se omite mensaje a %s", phone)
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
        _log_notification(channel="whatsapp", to=phone, subject="", ok=True, event_type=log_event)
        return True
    except Exception:
        logger.exception("Error enviando WhatsApp a %s", phone)
        _log_notification(channel="whatsapp", to=phone, subject="", ok=False, event_type=log_event)
        return False


def _log_notification(*, channel: str, to: str, subject: str, ok: bool, event_type: str) -> None:
    """Escribe la entrada en el log de notificaciones del tenant activo (no bloquea)."""
    try:
        from app.core.notification_config import append_notification_log
        append_notification_log(
            event_type=event_type,
            channel=channel,
            to=to,
            subject=subject,
            ok=ok,
        )
    except Exception:
        pass  # El log no debe interrumpir el flujo principal


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
        await send_email(email, subject, body, log_event="low_stock")


async def notify_overdue_loan(loan, tool, borrower) -> None:
    """Avisa al responsable de un préstamo que acaba de marcarse como vencido."""
    subject = f"Préstamo vencido: {tool.name}"
    body = (
        f"Hola {borrower.full_name},\n\n"
        f'El préstamo de "{tool.name}" venció el {loan.due_date.strftime("%d/%m/%Y")}.\n'
        f"Por favor devolvé la herramienta al pañol a la brevedad.\n\n"
        f"Este es un aviso automático de Pañol."
    )
    await send_email(borrower.email, subject, body, log_event="overdue")
    if borrower.phone:
        await send_whatsapp(borrower.phone, body, log_event="overdue")
