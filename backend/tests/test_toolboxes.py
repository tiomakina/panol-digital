"""Pruebas de cajas de herramientas: creación, agregar/quitar herramientas, exclusividad."""
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
