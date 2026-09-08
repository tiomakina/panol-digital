"""
API de Notificaciones — configuración de canales y log de envíos.
Endpoint: /api/v1/notifications/
Solo accesible para el rol Jefe.
"""
import httpx
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
    evolution_configured,
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


class WhatsAppTestRequest(BaseModel):
    phone: str  # Ej: "+56912345678" o "56912345678"


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/whatsapp/status")
async def get_whatsapp_status(
    user: User = Depends(require_role("jefe")),
):
    """
    Estado de la conexión de WhatsApp (Evolution API).
    Devuelve: estado de conexión y, si no está conectado, el QR en base64.
    """
    from app.core.config import settings as cfg

    if not evolution_configured():
        return {
            "backend": "none",
            "configured": False,
            "connected": False,
            "state": "not_configured",
            "qr": None,
        }

    base = cfg.EVOLUTION_API_URL.rstrip("/")
    instance = cfg.EVOLUTION_INSTANCE
    headers = {"apikey": cfg.EVOLUTION_API_KEY}

    # ── WAHA API (devlikeapro/waha) ──────────────────────────────────────────
    # Auth: X-Api-Key header
    # Estado sesión: GET /api/sessions/{instance}  → {"status": "WORKING"|"SCAN_QR_CODE"|...}
    # QR:           GET /api/{instance}/auth/qr    → {"mimetype":"image/png","data":"base64..."}
    # Start:        POST /api/sessions             → {"name": instance, "start": true}
    waha_headers = {"X-Api-Key": cfg.EVOLUTION_API_KEY, "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            # 1. Verificar estado de la sesión
            r = await client.get(f"{base}/api/sessions/{instance}", headers=waha_headers)

            if r.status_code == 404:
                # Sesión no existe — crearla y arrancarla
                cr = await client.post(
                    f"{base}/api/sessions",
                    headers=waha_headers,
                    json={"name": instance, "start": True},
                )
                if cr.status_code not in (200, 201):
                    return {"backend": "waha", "configured": True, "connected": False,
                            "state": "error", "error": cr.text, "qr": None}

            # 2. Leer estado actual
            r2 = await client.get(f"{base}/api/sessions/{instance}", headers=waha_headers)
            sess = r2.json() if r2.status_code == 200 else {}
            status = sess.get("status", "UNKNOWN")
            connected = status == "WORKING"

            if connected:
                return {"backend": "waha", "configured": True, "connected": True,
                        "state": "open", "qr": None}

            # 3. No conectado — pedir QR
            qr_res = await client.get(f"{base}/api/{instance}/auth/qr", headers=waha_headers)
            qr_data = qr_res.json() if qr_res.status_code == 200 else {}
            # WAHA devuelve {"mimetype": "image/png", "data": "base64..."}
            qr_b64 = qr_data.get("data")
            if qr_b64 and not qr_b64.startswith("data:"):
                qr_b64 = f"data:{qr_data.get('mimetype','image/png')};base64,{qr_b64}"

            return {
                "backend": "waha",
                "configured": True,
                "connected": False,
                "state": status,
                "qr": qr_b64,
            }
    except Exception as exc:
        return {"backend": "waha", "configured": True, "connected": False,
                "state": "error", "error": str(exc), "qr": None}


@router.post("/test-whatsapp")
async def send_test_whatsapp(
    body: WhatsAppTestRequest,
    user: User = Depends(require_role("jefe")),
):
    """
    Envía un mensaje de WhatsApp de prueba al número indicado.
    Devuelve el error exacto si falla (útil para diagnóstico).
    """
    from app.services.notification_service import send_whatsapp_with_error

    phone = (body.phone or "").strip()
    if not phone:
        raise HTTPException(400, "Ingresá un número de teléfono (ej: +56912345678)")

    message = (
        f"✅ Pañol 360 — Prueba de WhatsApp\n\n"
        f"Hola {user.full_name},\n"
        "Este mensaje confirma que la integración de WhatsApp funciona correctamente.\n\n"
        "— Pañol 360"
    )
    ok, err = await send_whatsapp_with_error(phone, message, log_event="test")
    if not ok:
        detail = "No se pudo enviar el mensaje de WhatsApp."
        if err:
            detail += f" Error: {err}"
        raise HTTPException(503, detail)
    return {"ok": True, "message": f"WhatsApp de prueba enviado a {phone}"}


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
