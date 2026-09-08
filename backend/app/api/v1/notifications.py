"""
API de Notificaciones — configuración de canales y log de envíos.
Endpoint: /api/v1/notifications/
Solo accesible para el rol Jefe.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import require_role
from app.models.user import User
from app.core.notification_config import (
    load_notification_config,
    save_notification_config,
    load_notification_log,
)
from app.services.notification_service import (
    email_configured,
    whatsapp_configured,
)

router = APIRouter(prefix="/notifications", tags=["Notificaciones"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class NotificationConfig(BaseModel):
    email_enabled: bool = True
    whatsapp_enabled: bool = False
    notify_overdue: bool = True
    notify_reminder: bool = True
    notify_low_stock: bool = True
    # Lista de emails que reciben copias de las alertas (reemplaza admin_email)
    admin_emails: list[str] = []


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/config")
async def get_notification_config(
    user: User = Depends(require_role("jefe")),
):
    """
    Devuelve la configuración de notificaciones del tenant activo,
    junto al estado de los canales (si SMTP y WhatsApp están configurados
    en las variables de entorno del servidor).
    """
    cfg = load_notification_config()
    return {
        **cfg,
        # Estado real de los canales en el servidor (solo lectura)
        "smtp_server_configured": email_configured(),
        "whatsapp_server_configured": whatsapp_configured(),
    }


@router.put("/config")
async def update_notification_config(
    body: NotificationConfig,
    user: User = Depends(require_role("jefe")),
):
    """Actualiza la configuración de notificaciones del tenant activo."""
    cfg = load_notification_config()
    cfg.update(body.model_dump())
    save_notification_config(cfg)
    return {"ok": True, "config": cfg}


@router.get("/log")
async def get_notification_log(
    limit: int = 50,
    user: User = Depends(require_role("jefe")),
):
    """
    Retorna las últimas `limit` notificaciones enviadas (o intentadas)
    para el tenant activo. Más reciente primero.
    """
    if limit < 1 or limit > 200:
        raise HTTPException(400, "limit debe estar entre 1 y 200")
    entries = load_notification_log(limit=limit)
    return {"count": len(entries), "entries": entries}


@router.post("/test")
async def send_test_notification(
    user: User = Depends(require_role("jefe")),
):
    """
    Envía una notificación de prueba al email del Jefe activo.
    El log se escribe automáticamente dentro de send_email.
    Devuelve el error exacto de SMTP para facilitar el diagnóstico.
    """
    from app.services.notification_service import send_email

    if not user.email:
        raise HTTPException(400, "Tu perfil no tiene email configurado — agrégalo en Usuarios primero.")

    subject = "✅ Pañol 360 — Prueba de notificación"
    body = (
        f"Hola {user.full_name},\n\n"
        "Esta es una notificación de prueba de Pañol 360.\n"
        "Si recibiste este email, el canal de email está funcionando correctamente.\n\n"
        "— Pañol 360"
    )
    ok, err = await send_email(user.email, subject, body, log_event="test")
    if not ok:
        detail = "No se pudo enviar el email de prueba."
        if err:
            detail += f" Error SMTP: {err}"
        raise HTTPException(503, detail)
    return {"ok": True, "message": f"Email de prueba enviado a {user.email}"}
