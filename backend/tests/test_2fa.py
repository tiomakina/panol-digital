"""Pruebas de 2FA (TOTP): setup, activación, login en dos pasos, desactivación."""
import pyotp

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole
from rut_test_helper import fake_rut


async def _create_user(email: str, password: str, role: UserRole = UserRole.jefe) -> None:
    async with AsyncSessionLocal() as db:
        db.add(User(email=email, rut=fake_rut(email), full_name="Jefe 2FA", role=role, hashed_password=hash_password(password)))
        await db.commit()


async def _login(client, email, password):
    return await client.post("/api/v1/auth/login", data={"username": fake_rut(email), "password": password})


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_login_without_2fa_returns_tokens_directly(client):
    await _create_user("sin2fa@test.com", "Clave123!")
    res = await _login(client, "sin2fa@test.com", "Clave123!")
    assert res.status_code == 200
    body = res.json()
    assert "access_token" in body
    assert "requires_2fa" not in body


async def test_full_2fa_enrollment_and_login_flow(client):
    await _create_user("jefe2fa@test.com", "Clave123!")
    login1 = await _login(client, "jefe2fa@test.com", "Clave123!")
    access_token = login1.json()["access_token"]

    # 1. Pedir el QR/secreto
    setup = await client.post("/api/v1/auth/2fa/setup", headers=_auth(access_token))
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    assert setup.json()["qr_code_base64"]

    # 2. Activar con un código válido generado a partir del secreto
    code = pyotp.TOTP(secret).now()
    enable = await client.post("/api/v1/auth/2fa/enable", json={"code": code}, headers=_auth(access_token))
    assert enable.status_code == 200, enable.text

    # 3. A partir de ahora, el login normal NO da tokens — pide 2FA
    login2 = await _login(client, "jefe2fa@test.com", "Clave123!")
    assert login2.status_code == 200
    body = login2.json()
    assert body.get("requires_2fa") is True
    temp_token = body["temp_token"]

    # 4. Código incorrecto rechazado
    bad = await client.post("/api/v1/auth/2fa/verify", json={"temp_token": temp_token, "code": "000000"})
    assert bad.status_code == 401

    # 5. Código correcto entrega tokens reales
    good_code = pyotp.TOTP(secret).now()
    verified = await client.post("/api/v1/auth/2fa/verify", json={"temp_token": temp_token, "code": good_code})
    assert verified.status_code == 200, verified.text
    assert "access_token" in verified.json()

    # 6. El temp_token es de un solo uso — reutilizarlo debe fallar
    reused = await client.post("/api/v1/auth/2fa/verify", json={"temp_token": temp_token, "code": good_code})
    assert reused.status_code == 401


async def test_disable_2fa_requires_correct_password(client):
    await _create_user("disable2fa@test.com", "Clave123!")
    login1 = await _login(client, "disable2fa@test.com", "Clave123!")
    access_token = login1.json()["access_token"]

    setup = await client.post("/api/v1/auth/2fa/setup", headers=_auth(access_token))
    secret = setup.json()["secret"]
    await client.post("/api/v1/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()}, headers=_auth(access_token))

    wrong = await client.post("/api/v1/auth/2fa/disable", json={"password": "incorrecta"}, headers=_auth(access_token))
    assert wrong.status_code == 400

    ok = await client.post("/api/v1/auth/2fa/disable", json={"password": "Clave123!"}, headers=_auth(access_token))
    assert ok.status_code == 200

    # Vuelve a loguear sin pedir 2FA
    login2 = await _login(client, "disable2fa@test.com", "Clave123!")
    assert "access_token" in login2.json()


async def test_enable_2fa_rejects_wrong_code(client):
    await _create_user("codewrong@test.com", "Clave123!")
    login1 = await _login(client, "codewrong@test.com", "Clave123!")
    access_token = login1.json()["access_token"]

    await client.post("/api/v1/auth/2fa/setup", headers=_auth(access_token))
    res = await client.post("/api/v1/auth/2fa/enable", json={"code": "000000"}, headers=_auth(access_token))
    assert res.status_code == 400
