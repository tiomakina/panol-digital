"""
Motor de configuración de notificaciones — por tenant.
Cada empresa tiene su propio archivo de configuración en:
  uploads/{tenant_id}/notification_config.json

Y su propio log de notificaciones enviadas en:
  uploads/{tenant_id}/notification_log.json

Similar al patrón de branding.py: las funciones leen el tenant
activo desde el ContextVar cuando no se pasa explícitamente.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.config import settings

UPLOAD_DIR = Path(settings.UPLOAD_DIR)

# ── Configuración por defecto ──────────────────────────────────────────────────

DEFAULT_NOTIFICATION_CONFIG: dict = {
    "email_enabled": True,
    "whatsapp_enabled": False,
    "notify_overdue": True,    # Avisar cuando préstamo vence
    "notify_reminder": True,   # Recordatorio 1 día antes del vencimiento
    "notify_low_stock": True,  # Avisar cuando stock mínimo se alcanza
    "admin_email": "",         # Email adicional del Jefe para recibir resúmenes
}

# Máximo de entradas en el log de notificaciones (rotación FIFO)
MAX_LOG_ENTRIES = 200


# ── Helpers de paths ───────────────────────────────────────────────────────────

def _get_config_file(tenant_id: Optional[str] = None) -> Path:
    if tenant_id is None:
        from app.core.tenant import get_current_tenant
        tenant_id = get_current_tenant()
    if tenant_id:
        return UPLOAD_DIR / tenant_id / "notification_config.json"
    return UPLOAD_DIR / "notification_config.json"


def _get_log_file(tenant_id: Optional[str] = None) -> Path:
    if tenant_id is None:
        from app.core.tenant import get_current_tenant
        tenant_id = get_current_tenant()
    if tenant_id:
        return UPLOAD_DIR / tenant_id / "notification_log.json"
    return UPLOAD_DIR / "notification_log.json"


# ── Config ─────────────────────────────────────────────────────────────────────

def load_notification_config(tenant_id: Optional[str] = None) -> dict:
    """Carga la configuración de notificaciones del tenant activo."""
    cfg_file = _get_config_file(tenant_id)
    if cfg_file.exists():
        try:
            with open(cfg_file) as f:
                return {**DEFAULT_NOTIFICATION_CONFIG, **json.load(f)}
        except Exception:
            pass
    return DEFAULT_NOTIFICATION_CONFIG.copy()


def save_notification_config(config: dict, tenant_id: Optional[str] = None) -> None:
    """Guarda la configuración de notificaciones del tenant activo."""
    cfg_file = _get_config_file(tenant_id)
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg_file, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# ── Log ────────────────────────────────────────────────────────────────────────

def load_notification_log(tenant_id: Optional[str] = None, limit: int = 50) -> list[dict]:
    """Carga las últimas `limit` entradas del log de notificaciones."""
    log_file = _get_log_file(tenant_id)
    if log_file.exists():
        try:
            with open(log_file) as f:
                entries = json.load(f)
            return entries[-limit:][::-1]  # Más reciente primero
        except Exception:
            pass
    return []


def append_notification_log(
    *,
    event_type: str,   # "overdue" | "reminder" | "low_stock" | "test"
    channel: str,      # "email" | "whatsapp"
    to: str,           # destinatario
    subject: str = "",
    ok: bool,
    extra: Optional[dict] = None,
    tenant_id: Optional[str] = None,
) -> None:
    """
    Agrega una entrada al log de notificaciones.
    Rota automáticamente para no superar MAX_LOG_ENTRIES.
    """
    log_file = _get_log_file(tenant_id)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Leer log actual
    entries: list[dict] = []
    if log_file.exists():
        try:
            with open(log_file) as f:
                entries = json.load(f)
        except Exception:
            entries = []

    # Agregar nueva entrada
    entry: dict = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "type": event_type,
        "channel": channel,
        "to": to,
        "subject": subject,
        "ok": ok,
    }
    if extra:
        entry.update(extra)
    entries.append(entry)

    # Rotar si supera el máximo
    if len(entries) > MAX_LOG_ENTRIES:
        entries = entries[-MAX_LOG_ENTRIES:]

    with open(log_file, "w") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
