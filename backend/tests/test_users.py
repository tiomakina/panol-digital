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
    # Encargado (y Jefe) pueden editar sus propios datos de contacto, pero
    # no su propio rol/estado — un Mecánico ya no puede ni lo primero, ver
    # test_mecanico_cannot_edit_own_profile.
    await _create_user("encargado2@test.com", "Clave123!", UserRole.encargado)
    token = await _login(client, "encargado2@test.com", "Clave123!")
    me = (await client.get("/api/v1/auth/me", headers=_auth(token))).json()

    ok = await client.put(f"/api/v1/users/{me['id']}", json={"phone": "555-1234"}, headers=_auth(token))
    assert ok.status_code == 200
    assert ok.json()["phone"] == "555-1234"

    escalate = await client.put(f"/api/v1/users/{me['id']}", json={"role": "jefe"}, headers=_auth(token))
    assert escalate.status_code == 403


async def test_mecanico_cannot_edit_own_profile(client):
    """
    Pedido del cliente: un Mecánico puede VER su perfil (vía /auth/me) pero
    no editarlo — a diferencia de Encargado/Jefe. Antes cualquier rol podía
    editar sus propios datos de contacto.
    """
    await _create_user("meca_noedit@test.com", "Clave123!", UserRole.mecanico)
    token = await _login(client, "meca_noedit@test.com", "Clave123!")
    me = (await client.get("/api/v1/auth/me", headers=_auth(token))).json()

    blocked = await client.put(f"/api/v1/users/{me['id']}", json={"phone": "555-9999"}, headers=_auth(token))
    assert blocked.status_code == 403


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
    # Encargado sí puede subir su propia foto (a diferencia de Mecánico,
    # ver test_mecanico_cannot_upload_own_photo).
    await _create_user("enc_foto@test.com", "Clave123!", UserRole.encargado)
    await _create_user("meca_foto@test.com", "Clave123!", UserRole.mecanico)
    await _create_user("jefe_foto@test.com", "Clave123!", UserRole.jefe)
    encargado_token = await _login(client, "enc_foto@test.com", "Clave123!")
    jefe_token = await _login(client, "jefe_foto@test.com", "Clave123!")
    meca_token = await _login(client, "meca_foto@test.com", "Clave123!")

    enc_id = (await client.get("/api/v1/auth/me", headers=_auth(encargado_token))).json()["id"]
    meca_id = (await client.get("/api/v1/auth/me", headers=_auth(meca_token))).json()["id"]

    own_upload = await client.post(
        f"/api/v1/users/{enc_id}/photo",
        files={"file": ("foto.png", _fake_png(), "image/png")},
        headers=_auth(encargado_token),
    )
    assert own_upload.status_code == 200, own_upload.text
    assert own_upload.json()["avatar_url"].startswith("/static/uploads/avatars/")

    # Un jefe puede subirle la foto a otro usuario (incluso un Mecánico,
    # que no puede subir la suya propia)
    jefe_uploads_for_meca = await client.post(
        f"/api/v1/users/{meca_id}/photo",
        files={"file": ("foto2.png", _fake_png(), "image/png")},
        headers=_auth(jefe_token),
    )
    assert jefe_uploads_for_meca.status_code == 200


async def test_mecanico_cannot_upload_own_photo(client):
    await _create_user("meca_foto2@test.com", "Clave123!", UserRole.mecanico)
    token = await _login(client, "meca_foto2@test.com", "Clave123!")
    meca_id = (await client.get("/api/v1/auth/me", headers=_auth(token))).json()["id"]

    blocked = await client.post(
        f"/api/v1/users/{meca_id}/photo",
        files={"file": ("foto.png", _fake_png(), "image/png")},
        headers=_auth(token),
    )
    assert blocked.status_code == 403


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


async def test_mecanico_cannot_list_and_cannot_edit_own_profile(client):
    """
    Documenta el contrato a propósito: un Mecánico NO puede ver el listado
    completo de usuarios (GET /users requiere Encargado+, no debería ver el
    directorio de todo el equipo) NI editar su propio perfil (a diferencia
    de Encargado/Jefe) — solo puede VERLO vía GET /auth/me. Para editar
    algo (nombre, teléfono, foto) tiene que pedírselo a un Encargado o
    Jefe.
    """
    await _create_user("meca_perfil@test.com", "Clave123!", UserRole.mecanico)
    token = await _login(client, "meca_perfil@test.com", "Clave123!")
    me = (await client.get("/api/v1/auth/me", headers=_auth(token))).json()
    assert me["full_name"] == "Seed"

    listing = await client.get("/api/v1/users", headers=_auth(token))
    assert listing.status_code == 403

    own_upload = await client.post(
        f"/api/v1/users/{me['id']}/photo",
        files={"file": ("foto.png", _fake_png(), "image/png")},
        headers=_auth(token),
    )
    assert own_upload.status_code == 403

    own_edit = await client.put(
        f"/api/v1/users/{me['id']}", json={"full_name": "Mecánico Actualizado"}, headers=_auth(token)
    )
    assert own_edit.status_code == 403


async def test_photo_upload_rejects_non_image_file(client):
    # Encargado (no Mecánico, que ya ni llega a la validación de archivo —
    # ver test_mecanico_cannot_upload_own_photo) subiendo su propia foto.
    await _create_user("enc_bad@test.com", "Clave123!", UserRole.encargado)
    token = await _login(client, "enc_bad@test.com", "Clave123!")
    user_id = (await client.get("/api/v1/auth/me", headers=_auth(token))).json()["id"]

    res = await client.post(
        f"/api/v1/users/{user_id}/photo",
        files={"file": ("archivo.txt", b"esto no es una imagen", "text/plain")},
        headers=_auth(token),
    )
    assert res.status_code == 400
