"""Pruebas del servicio de notificaciones — sin configurar no debe romper nada."""
from datetime import date
from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.services import notification_service as ns


class _FakeTool:
    name = "Taladro"


class _FakeUser:
    full_name = "Juan Pérez"
    email = "juan@test.com"
    phone = None


class _FakeLoan:
    due_date = date(2026, 1, 1)


def test_email_not_configured_by_default():
    assert ns.email_configured() is False


def test_whatsapp_not_configured_by_default():
    assert ns.whatsapp_configured() is False


async def test_send_email_noop_when_not_configured():
    assert await ns.send_email("x@test.com", "asunto", "cuerpo") is False


async def test_send_whatsapp_noop_when_not_configured():
    assert await ns.send_whatsapp("+5491122334455", "hola") is False


async def test_notify_overdue_loan_does_not_raise_without_config():
    # No debe explotar aunque ningún canal esté configurado — es el camino
    # que toma app/tasks/loan_tasks.py en un despliegue sin SMTP/WhatsApp.
    await ns.notify_overdue_loan(_FakeLoan(), _FakeTool(), _FakeUser())


async def test_send_email_success_path(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.com")
    monkeypatch.setattr(settings, "SMTP_USER", "bot@test.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "secret")
    assert ns.email_configured() is True

    with patch("app.services.notification_service.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        ok = await ns.send_email("dest@test.com", "asunto", "cuerpo")
    assert ok is True
    mock_send.assert_awaited_once()


async def test_send_email_returns_false_on_error(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.com")
    monkeypatch.setattr(settings, "SMTP_USER", "bot@test.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "secret")

    with patch("app.services.notification_service.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        mock_send.side_effect = OSError("conexión rechazada")
        ok = await ns.send_email("dest@test.com", "asunto", "cuerpo")
    assert ok is False


async def test_send_whatsapp_success_path(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_API_TOKEN", "token123")
    monkeypatch.setattr(settings, "WHATSAPP_PHONE_ID", "phoneid123")
    assert ns.whatsapp_configured() is True

    class _FakeResponse:
        def raise_for_status(self):
            pass

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _FakeResponse()
        ok = await ns.send_whatsapp("+5491122334455", "hola")
    assert ok is True
    mock_post.assert_awaited_once()
