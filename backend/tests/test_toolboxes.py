"""Pruebas de cajas de herramientas: creación, agregar/quitar herramientas, exclusividad, responsable."""
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole
from rut_test_helper import fake_rut


async def _create_user_full(email: str, password: str, role: UserRole, full_name: str = "Seed") -> int:
    async with AsyncSessionLocal() as db:
        user = User(email=email, rut=fake_rut(email), full_name=full_name, role=role, hashed_password=hash_password(password))
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.id


async def _create_user(email: str, password: str, role: UserRole) -> None:
    async with AsyncSessionLocal() as db:
        db.add(User(email=email, rut=fake_rut(email), full_name="Seed", role=role, hashed_password=hash_password(password)))
        await db.commit()


async def _login(client, email, password) -> str:
    res = await client.post("/api/v1/auth/login", data={"username": fake_rut(email), "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_toolbox_lifecycle(client):
    await _create_user("jefe@test.com", "Clave123!", UserRole.jefe)
    jefe_token = await _login(client, "jefe@test.com", "Clave123!")

    tool1 = (await client.post(
        "/api/v1/tools", json={"name": "Martillo"}, headers=_auth(jefe_token)
    )).json()
    tool2 = (await client.post(
        "/api/v1/tools", json={"name": "Destornillador"}, headers=_auth(jefe_token)
    )).json()

    toolbox = (await client.post(
        "/api/v1/toolboxes",
        json={"name": "Caja Electricista", "location": "Depósito A"},
        headers=_auth(jefe_token),
    ))
    assert toolbox.status_code == 201, toolbox.text
    toolbox = toolbox.json()
    assert toolbox["qr_code_url"]
    toolbox_id = toolbox["id"]

    add1 = await client.post(
        f"/api/v1/toolboxes/{toolbox_id}/tools", params={"tool_id": tool1["id"]}, headers=_auth(jefe_token)
    )
    assert add1.status_code == 201, add1.text
    assert len(add1.json()["items"]) == 1

    add2 = await client.post(
        f"/api/v1/toolboxes/{toolbox_id}/tools", params={"tool_id": tool2["id"]}, headers=_auth(jefe_token)
    )
    assert len(add2.json()["items"]) == 2

    # Otra caja no puede robarse una herramienta ya asignada
    other_box = (await client.post(
        "/api/v1/toolboxes", json={"name": "Otra caja"}, headers=_auth(jefe_token)
    )).json()
    dup = await client.post(
        f"/api/v1/toolboxes/{other_box['id']}/tools", params={"tool_id": tool1["id"]}, headers=_auth(jefe_token)
    )
    assert dup.status_code == 400

    remove = await client.delete(
        f"/api/v1/toolboxes/{toolbox_id}/tools/{tool1['id']}", headers=_auth(jefe_token)
    )
    assert remove.status_code == 200
    assert len(remove.json()["items"]) == 1

    # Ahora que se liberó, sí se puede mover a la otra caja
    moved = await client.post(
        f"/api/v1/toolboxes/{other_box['id']}/tools", params={"tool_id": tool1["id"]}, headers=_auth(jefe_token)
    )
    assert moved.status_code == 201

    deleted = await client.delete(f"/api/v1/toolboxes/{toolbox_id}", headers=_auth(jefe_token))
    assert deleted.status_code == 204

    missing = await client.get(f"/api/v1/toolboxes/{toolbox_id}", headers=_auth(jefe_token))
    assert missing.status_code == 404


async def test_toolbox_responsible_mechanic(client):
    await _create_user_full("jefe2@test.com", "Clave123!", UserRole.jefe)
    jefe_token = await _login(client, "jefe2@test.com", "Clave123!")
    mecanico_id = await _create_user_full("meca@test.com", "Clave123!", UserRole.mecanico, "Juan Mecánico")

    # Crear con responsable asignado desde el inicio
    created = await client.post(
        "/api/v1/toolboxes",
        json={"name": "Caja Plomería", "responsible_user_id": mecanico_id},
        headers=_auth(jefe_token),
    )
    assert created.status_code == 201, created.text
    box = created.json()
    assert box["responsible"]["full_name"] == "Juan Mecánico"
    assert box["responsible_user_id"] == mecanico_id

    # Un id de usuario inexistente debe rechazarse
    invalid = await client.post(
        "/api/v1/toolboxes",
        json={"name": "Caja X", "responsible_user_id": 999999},
        headers=_auth(jefe_token),
    )
    assert invalid.status_code == 404

    # Reasignar el responsable vía update
    other_id = await _create_user_full("meca2@test.com", "Clave123!", UserRole.mecanico, "Ana Mecánica")
    updated = await client.put(
        f"/api/v1/toolboxes/{box['id']}",
        json={"responsible_user_id": other_id},
        headers=_auth(jefe_token),
    )
    assert updated.status_code == 200
    assert updated.json()["responsible"]["full_name"] == "Ana Mecánica"

    # Quitar el responsable (volver a null)
    cleared = await client.put(
        f"/api/v1/toolboxes/{box['id']}",
        json={"responsible_user_id": None},
        headers=_auth(jefe_token),
    )
    assert cleared.status_code == 200
    assert cleared.json()["responsible"] is None
