"""Pruebas de gestión de usuarios: alta, edición, roles, activación y cambio de contraseña."""
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole


async def _create_user(email: str, password: str, role: UserRole) -> None:
    async with AsyncSessionLocal() as db:
        db.add(User(email=email, full_name="Seed", role=role, hashed_password=hash_password(password)))
        await db.commit()


async def _login(client, email, password) -> str:
    res = await client.post("/api/v1/auth/login", data={"username": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_only_jefe_can_create_users(client):
    await _create_user("jefe@test.com", "Clave123!", UserRole.jefe)
    await _create_user("encargado@test.com", "Clave123!", UserRole.encargado)

    jefe_token = await _login(client, "jefe@test.com", "Clave123!")
    encargado_token = await _login(client, "encargado@test.com", "Clave123!")

    forbidden = await client.post(
        "/api/v1/users",
        json={"email": "nuevo@test.com", "full_name": "Nuevo", "role": "mecanico", "password": "Clave123!"},
        headers=_auth(encargado_token),
    )
    assert forbidden.status_code == 403

    created = await client.post(
        "/api/v1/users",
        json={"email": "nuevo@test.com", "full_name": "Nuevo", "role": "mecanico", "password": "Clave123!"},
        headers=_auth(jefe_token),
    )
    assert created.status_code == 201, created.text
    assert created.json()["role"] == "mecanico"

    # No se puede repetir el email
    dup = await client.post(
        "/api/v1/users",
        json={"email": "nuevo@test.com", "full_name": "Otro", "role": "mecanico", "password": "Clave123!"},
        headers=_auth(jefe_token),
    )
    assert dup.status_code == 400


async def test_user_can_edit_own_profile_but_not_own_role(client):
    await _create_user("mecanico2@test.com", "Clave123!", UserRole.mecanico)
    token = await _login(client, "mecanico2@test.com", "Clave123!")
    me = (await client.get("/api/v1/auth/me", headers=_auth(token))).json()

    ok = await client.put(f"/api/v1/users/{me['id']}", json={"phone": "555-1234"}, headers=_auth(token))
    assert ok.status_code == 200
    assert ok.json()["phone"] == "555-1234"

    escalate = await client.put(f"/api/v1/users/{me['id']}", json={"role": "jefe"}, headers=_auth(token))
    assert escalate.status_code == 403


async def test_jefe_can_change_role_and_deactivate(client):
    await _create_user("jefe2@test.com", "Clave123!", UserRole.jefe)
    await _create_user("mecanico3@test.com", "Clave123!", UserRole.mecanico)

    jefe_token = await _login(client, "jefe2@test.com", "Clave123!")
    target = (await client.get("/api/v1/users", params={"search": "mecanico3"}, headers=_auth(jefe_token))).json()[0]

    promoted = await client.put(
        f"/api/v1/users/{target['id']}", json={"role": "encargado"}, headers=_auth(jefe_token)
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "encargado"

    deactivated = await client.post(f"/api/v1/users/{target['id']}/deactivate", headers=_auth(jefe_token))
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    # Ya no puede iniciar sesión
    blocked_login = await client.post(
        "/api/v1/auth/login", data={"username": "mecanico3@test.com", "password": "Clave123!"}
    )
    assert blocked_login.status_code == 403

    reactivated = await client.post(f"/api/v1/users/{target['id']}/reactivate", headers=_auth(jefe_token))
    assert reactivated.status_code == 200
    assert reactivated.json()["is_active"] is True


async def test_jefe_cannot_deactivate_self(client):
    await _create_user("jefe3@test.com", "Clave123!", UserRole.jefe)
    token = await _login(client, "jefe3@test.com", "Clave123!")
    me = (await client.get("/api/v1/auth/me", headers=_auth(token))).json()

    res = await client.post(f"/api/v1/users/{me['id']}/deactivate", headers=_auth(token))
    assert res.status_code == 400


async def test_change_own_password(client):
    await _create_user("cambiaclave@test.com", "ClaveVieja1!", UserRole.mecanico)
    token = await _login(client, "cambiaclave@test.com", "ClaveVieja1!")

    wrong = await client.put(
        "/api/v1/users/me/password",
        json={"current_password": "incorrecta", "new_password": "ClaveNueva1!"},
        headers=_auth(token),
    )
    assert wrong.status_code == 400

    ok = await client.put(
        "/api/v1/users/me/password",
        json={"current_password": "ClaveVieja1!", "new_password": "ClaveNueva1!"},
        headers=_auth(token),
    )
    assert ok.status_code == 200

    relogin = await client.post(
        "/api/v1/auth/login", data={"username": "cambiaclave@test.com", "password": "ClaveNueva1!"}
    )
    assert relogin.status_code == 200
