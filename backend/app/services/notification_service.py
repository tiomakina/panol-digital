"""
Servicio de Notificaciones — avisa por email y/o WhatsApp cuando corresponde
(hoy: préstamos vencidos, disparado desde app/tasks/loan_tasks.py).

Ambos canales son opcionales (así están documentados en .env.example): si
no están configurados, se omiten en silencio — nunca deben romper el flujo
de Celery ni el de la API.

La configuración por tenant (email_enabled, whatsapp_enabled) se lee desde
notification_config.py — cada empresa puede activar/desactivar canales desde
la pantalla de Notificaciones en Administración.

WhatsApp — dos backends soportados (en orden de preferencia):
  1. Evolution API (self-hosted, recomendado): EVOLUTION_API_KEY configurado.
     El Jefe escanea un QR con su celular una vez y el sistema puede enviar
     a cualquier número sin cuenta Meta Business.
  2. Meta Business Cloud API (legacy): WHATSAPP_API_TOKEN + WHATSAPP_PHONE_ID.
     Requiere cuenta empresarial verificada en Meta for Developers.
"""
import logging
import re

import aiosmtplib
import httpx
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger("panol.notifications")


def email_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD)


def evolution_configured() -> bool:
    """True si Evolution API está habilitada (backend recomendado para WhatsApp)."""
    return bool(settings.EVOLUTION_API_KEY)


def whatsapp_configured() -> bool:
    """True si hay algún backend de WhatsApp disponible (Evolution o Meta)."""
    return evolution_configured() or bool(settings.WHATSAPP_API_TOKEN and settings.WHATSAPP_PHONE_ID)


def _normalize_phone(phone: str) -> str:
    """
    Normaliza un número de teléfono para Evolution API:
    Elimina espacios, +, guiones, paréntesis.
    Ejemplo: "+56 9 1234 5678" → "56912345678"
    """
    return re.sub(r'[\s\+\-\(\)]', '', phone)


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


async def send_email(to: str, subject: str, body: str, log_event: str = "general") -> tuple[bool, str]:
    """
    Envía un email por SMTP.
    Devuelve (True, "") si OK, o (False, "mensaje de error") si falla.
    Nunca lanza excepción — los fallos se registran en el log del tenant.

    Modo TLS automático:
      - Puerto 465 → use_tls=True  (SSL/TLS implícito)
      - Cualquier otro puerto → start_tls=True (STARTTLS, típico en 587)
    """
    if not email_configured():
        msg = "SMTP no configurado en el servidor (faltan SMTP_HOST, SMTP_USER o SMTP_PASSWORD en .env)"
        logger.info("SMTP no configurado — se omite el email a %s (%s)", to, subject)
        return False, msg
    if not _notification_enabled("email"):
        msg = "Email desactivado en la configuración de notificaciones del tenant"
        logger.info("Email desactivado en config del tenant — se omite email a %s (%s)", to, subject)
        return False, msg
    try:
        message = EmailMessage()
        message["From"] = settings.SMTP_FROM or settings.SMTP_USER
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        # Puerto 465 = SSL/TLS directo; 587 u otros = STARTTLS
        use_ssl = int(settings.SMTP_PORT or 587) == 465
        kwargs: dict = dict(
            hostname=settings.SMTP_HOST,
            port=int(settings.SMTP_PORT or 587),
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
        )
        if use_ssl:
            kwargs["use_tls"] = True
        else:
            kwargs["start_tls"] = True

        await aiosmtplib.send(message, **kwargs)
        _log_notification(channel="email", to=to, subject=subject, ok=True, event_type=log_event)
        return True, ""
    except Exception as exc:
        err = str(exc)
        logger.exception("Error enviando email a %s", to)
        _log_notification(channel="email", to=to, subject=subject, ok=False, event_type=log_event)
        return False, err


async def _send_whatsapp_evolution(phone: str, message: str, log_event: str = "general") -> tuple[bool, str]:
    """
    Envía un mensaje vía WAHA (WhatsApp HTTP API, self-hosted).
    Formato de número: "56912345678@c.us" (agrega @c.us automáticamente).
    Devuelve (True, "") si OK, (False, error_str) si falla.
    """
    phone_clean = _normalize_phone(phone)
    # WAHA requiere el sufijo @c.us para chats individuales
    chat_id = phone_clean if phone_clean.endswith("@c.us") else f"{phone_clean}@c.us"

    url = f"{settings.EVOLUTION_API_URL}/api/sendText"
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": settings.EVOLUTION_API_KEY,
    }
    payload = {
        "chatId": chat_id,
        "text": message,
        "session": settings.EVOLUTION_INSTANCE,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(url, json=payload, headers=headers)
            res.raise_for_status()
        _log_notification(channel="whatsapp", to=phone, subject="", ok=True, event_type=log_event)
        return True, ""
    except Exception as exc:
        err = str(exc)
        logger.exception("Error enviando WhatsApp (WAHA) a %s", phone)
        _log_notification(channel="whatsapp", to=phone, subject="", ok=False, event_type=log_event)
        return False, err


async def _send_whatsapp_meta(phone: str, message: str, log_event: str = "general") -> tuple[bool, str]:
    """
    Envía un mensaje vía Meta Business Cloud API (legacy).
    Devuelve (True, "") si OK, (False, error_str) si falla.
    """
    url = f"https://graph.facebook.com/v18.0/{settings.WHATSAPP_PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {settings.WHATSAPP_API_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": _normalize_phone(phone),
        "type": "text",
        "text": {"body": message},
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(url, json=payload, headers=headers)
            res.raise_for_status()
        _log_notification(channel="whatsapp", to=phone, subject="", ok=True, event_type=log_event)
        return True, ""
    except Exception as exc:
        err = str(exc)
        logger.exception("Error enviando WhatsApp (Meta) a %s", phone)
        _log_notification(channel="whatsapp", to=phone, subject="", ok=False, event_type=log_event)
        return False, err


async def send_whatsapp(phone: str, message: str, log_event: str = "general") -> bool:
    """
    Envía un mensaje de WhatsApp usando el backend disponible:
      1. Evolution API (si EVOLUTION_API_KEY está configurado)
      2. Meta Business API (si WHATSAPP_API_TOKEN + WHATSAPP_PHONE_ID están configurados)
    Devuelve False (sin excepción) si no hay backend disponible o falla.
    """
    if not whatsapp_configured():
        logger.info("WhatsApp no configurado — se omite el mensaje a %s", phone)
        return False
    if not _notification_enabled("whatsapp"):
        logger.info("WhatsApp desactivado en config del tenant — se omite mensaje a %s", phone)
        return False

    if evolution_configured():
        ok, _ = await _send_whatsapp_evolution(phone, message, log_event)
        return ok
    else:
        ok, _ = await _send_whatsapp_meta(phone, message, log_event)
        return ok


async def send_whatsapp_with_error(phone: str, message: str, log_event: str = "general") -> tuple[bool, str]:
    """
    Igual que send_whatsapp pero devuelve (bool, error_str) — para endpoints de prueba.
    """
    if not whatsapp_configured():
        return False, "WhatsApp no configurado en el servidor (falta EVOLUTION_API_KEY o WHATSAPP_API_TOKEN)"
    if not _notification_enabled("whatsapp"):
        return False, "WhatsApp desactivado en la configuración de notificaciones del tenant"

    if evolution_configured():
        return await _send_whatsapp_evolution(phone, message, log_event)
    else:
        return await _send_whatsapp_meta(phone, message, log_event)


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


def _get_admin_emails() -> list[str]:
    """
    Devuelve la lista de emails de administración configurados en el tenant activo.
    Filtra vacíos y duplicados, sin lanzar excepciones.
    """
    try:
        from app.core.notification_config import load_notification_config
        cfg = load_notification_config()
        raw = cfg.get("admin_emails", [])
        return list(dict.fromkeys(e.strip() for e in raw if e and e.strip()))
    except Exception:
        return []


async def notify_low_stock(tool_name: str, available: int, min_stock: int, recipients: list[str]) -> None:
    """
    Avisa a los Encargados/Jefes cuando el stock disponible baja del mínimo.
    Envía a los recipients pasados Y a todos los admin_emails configurados.
    """
    subject = f"⚠ Stock mínimo alcanzado: {tool_name}"
    body = (
        f"Atención:\n\n"
        f'La herramienta "{tool_name}" tiene solo {available} unidad(es) disponible(s), '
        f"que está por debajo del mínimo configurado ({min_stock}).\n\n"
        f"Considera devolver o gestionar el reabastecimiento.\n\n"
        f"— Pañol 360"
    )
    # Unión sin duplicados: destinatarios directos + lista de admins configurados
    all_recipients = list(dict.fromkeys(recipients + _get_admin_emails()))
    for email in all_recipients:
        await send_email(email, subject, body, log_event="low_stock")


async def notify_overdue_loan(loan, tool, borrower) -> None:
    """
    Avisa al responsable de un préstamo que acaba de marcarse como vencido.
    Envía copia a todos los admin_emails configurados.
    """
    subject = f"Préstamo vencido: {tool.name}"
    body = (
        f"Hola {borrower.full_name},\n\n"
        f'El préstamo de "{tool.name}" venció el {loan.due_date.strftime("%d/%m/%Y")}.\n'
        f"Por favor devolvé la herramienta al pañol a la brevedad.\n\n"
        f"Este es un aviso automático de Pañol 360."
    )
    # Primero al responsable directo
    await send_email(borrower.email, subject, body, log_event="overdue")
    if borrower.phone:
        await send_whatsapp(borrower.phone, body, log_event="overdue")

    # Copia a administradores configurados (sin duplicar si coincide con el responsable)
    admin_subject = f"[Copia Jefe] Préstamo vencido: {tool.name}"
    admin_body = (
        f"Copia de alerta enviada a {borrower.full_name} ({borrower.email}):\n\n"
        + body
    )
    for admin_email in _get_admin_emails():
        if admin_email != borrower.email:
            await send_email(admin_email, admin_subject, admin_body, log_event="overdue")


async def send_whatsapp_raw(phone: str, message: str, log_event: str = "general") -> tuple[bool, str]:
    """Alias con firma consistente (bool, error_str) para send_whatsapp."""
    ok = await send_whatsapp(phone, message, log_event=log_event)
    return ok, ""
