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


def _fake_png() -> bytes:
    # Header PNG real (magic bytes) + relleno — alcanza para pasar la
    # validación de tipo real de archivo, no hace falta un PNG válido entero.
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


async def test_upload_own_photo_and_jefe_can_upload_for_others(client):
    await _create_user("meca_foto@test.com", "Clave123!", UserRole.mecanico)
    await _create_user("jefe_foto@test.com", "Clave123!", UserRole.jefe)
    mecanico_token = await _login(client, "meca_foto@test.com", "Clave123!")
    jefe_token = await _login(client, "jefe_foto@test.com", "Clave123!")

    meca_id = (await client.get("/api/v1/auth/me", headers=_auth(mecanico_token))).json()["id"]

    own_upload = await client.post(
        f"/api/v1/users/{meca_id}/photo",
        files={"file": ("foto.png", _fake_png(), "image/png")},
        headers=_auth(mecanico_token),
    )
    assert own_upload.status_code == 200, own_upload.text
    assert own_upload.json()["avatar_url"].startswith("/static/uploads/avatars/")

    # Un jefe puede subirle la foto a otro usuario
    jefe_uploads_for_meca = await client.post(
        f"/api/v1/users/{meca_id}/photo",
        files={"file": ("foto2.png", _fake_png(), "image/png")},
        headers=_auth(jefe_token),
    )
    assert jefe_uploads_for_meca.status_code == 200


async def test_cannot_upload_photo_for_another_user_without_being_jefe(client):
    await _create_user("meca_a@test.com", "Clave123!", UserRole.mecanico)
    await _create_user("meca_b@test.com", "Clave123!", UserRole.mecanico)
    token_a = await _login(client, "meca_a@test.com", "Clave123!")
    token_b = await _login(client, "meca_b@test.com", "Clave123!")
    meca_b_id = (await client.get("/api/v1/auth/me", headers=_auth(token_b))).json()["id"]

    forbidden = await client.post(
        f"/api/v1/users/{meca_b_id}/photo",
        files={"file": ("foto.png", _fake_png(), "image/png")},
        headers=_auth(token_a),
    )
    assert forbidden.status_code == 403


async def test_mecanico_cannot_list_but_can_still_edit_own_profile(client):
    """
    Documenta el contrato a propósito: un Mecánico NO puede ver el listado
    completo de usuarios (GET /users requiere Encargado+, es intencional —
    no debería ver el directorio de todo el equipo), pero SÍ tiene que
    poder editar sus propios datos y subir su propia foto sin importar el
    rol. Antes el frontend llamaba a loadUsers() sin importar el rol, y
    como devolvía 403 la tabla quedaba vacía sin explicación — parecía que
    el sistema no dejaba subir la foto, cuando el problema real era no
    poder LISTAR. La UI ahora usa GET /auth/me para el propio perfil en
    vez de depender del listado.
    """
    await _create_user("meca_perfil@test.com", "Clave123!", UserRole.mecanico)
    token = await _login(client, "meca_perfil@test.com", "Clave123!")
    me = (await client.get("/api/v1/auth/me", headers=_auth(token))).json()

    listing = await client.get("/api/v1/users", headers=_auth(token))
    assert listing.status_code == 403

    own_upload = await client.post(
        f"/api/v1/users/{me['id']}/photo",
        files={"file": ("foto.png", _fake_png(), "image/png")},
        headers=_auth(token),
    )
    assert own_upload.status_code == 200, own_upload.text

    own_edit = await client.put(
        f"/api/v1/users/{me['id']}", json={"full_name": "Mecánico Actualizado"}, headers=_auth(token)
    )
    assert own_edit.status_code == 200, own_edit.text
    assert own_edit.json()["full_name"] == "Mecánico Actualizado"


async def test_photo_upload_rejects_non_image_file(client):
    await _create_user("meca_bad@test.com", "Clave123!", UserRole.mecanico)
    token = await _login(client, "meca_bad@test.com", "Clave123!")
    user_id = (await client.get("/api/v1/auth/me", headers=_auth(token))).json()["id"]

    res = await client.post(
        f"/api/v1/users/{user_id}/photo",
        files={"file": ("archivo.txt", b"esto no es una imagen", "text/plain")},
        headers=_auth(token),
    )
    assert res.status_code == 400
