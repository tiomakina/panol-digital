"""Pruebas del flujo de autenticación: login, /me, refresh (rotación), logout, rate limiting."""
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole


async def _create_user(email: str, password: str, role: UserRole = UserRole.jefe) -> None:
    async with AsyncSessionLocal() as db:
        db.add(User(email=email, full_name="Usuario de prueba", role=role,
                     hashed_password=hash_password(password)))
        await db.commit()


async def test_login_success_and_me(client):
    await _create_user("jefe@test.com", "Clave123!")

    res = await client.post("/api/v1/auth/login", data={"username": "jefe@test.com", "password": "Clave123!"})
    assert res.status_code == 200, res.text
    tokens = res.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"] and tokens["refresh_token"]

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "jefe@test.com"


async def test_login_wrong_password(client):
    await _create_user("mecanico@test.com", "ClaveBuena1!", role=UserRole.mecanico)
    res = await client.post("/api/v1/auth/login", data={"username": "mecanico@test.com", "password": "incorrecta"})
    assert res.status_code == 401


async def test_login_unknown_user(client):
    res = await client.post("/api/v1/auth/login", data={"username": "nadie@test.com", "password": "loquesea"})
    assert res.status_code == 401


async def test_refresh_rotates_and_old_token_stops_working(client):
    await _create_user("encargado@test.com", "Clave123!", role=UserRole.encargado)
    login = await client.post("/api/v1/auth/login", data={"username": "encargado@test.com", "password": "Clave123!"})
    refresh_token = login.json()["refresh_token"]

    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != login.json()["access_token"]

    # El refresh token ya usado queda revocado (rotación) — reutilizarlo debe fallar
    reused = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert reused.status_code == 401


async def test_logout_revokes_access_token(client):
    await _create_user("logout@test.com", "Clave123!", role=UserRole.jefe)
    login = await client.post("/api/v1/auth/login", data={"username": "logout@test.com", "password": "Clave123!"})
    access_token = login.json()["access_token"]
    refresh_token = login.json()["refresh_token"]

    logout = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout.status_code == 200

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me.status_code == 401


async def test_login_rate_limit_blocks_after_too_many_attempts(client):
    for _ in range(5):
        await client.post("/api/v1/auth/login", data={"username": "bloqueado@test.com", "password": "mal"})

    blocked = await client.post("/api/v1/auth/login", data={"username": "bloqueado@test.com", "password": "mal"})
    assert blocked.status_code == 429
