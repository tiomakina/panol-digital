"""Pruebas de las tablas maestras (marca, categoría, ubicación, proveedor)."""
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole
from rut_test_helper import fake_rut


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


async def test_brand_crud_and_uniqueness(client):
    await _create_user("jefe_lk@test.com", "Clave123!", UserRole.jefe)
    await _create_user("meca_lk@test.com", "Clave123!", UserRole.mecanico)
    jefe_token = await _login(client, "jefe_lk@test.com", "Clave123!")
    meca_token = await _login(client, "meca_lk@test.com", "Clave123!")

    # Un mecánico puede leer pero no crear
    forbidden = await client.post("/api/v1/lookups/brands", json={"name": "Bosch"}, headers=_auth(meca_token))
    assert forbidden.status_code == 403

    created = await client.post("/api/v1/lookups/brands", json={"name": "Bosch"}, headers=_auth(jefe_token))
    assert created.status_code == 201, created.text
    brand_id = created.json()["id"]

    # No se puede repetir el nombre
    dup = await client.post("/api/v1/lookups/brands", json={"name": "Bosch"}, headers=_auth(jefe_token))
    assert dup.status_code == 400

    listed = await client.get("/api/v1/lookups/brands", headers=_auth(meca_token))
    assert listed.status_code == 200
    assert any(b["name"] == "Bosch" for b in listed.json())

    updated = await client.put(
        f"/api/v1/lookups/brands/{brand_id}", json={"name": "Bosch Professional"}, headers=_auth(jefe_token)
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Bosch Professional"

    deleted = await client.delete(f"/api/v1/lookups/brands/{brand_id}", headers=_auth(jefe_token))
    assert deleted.status_code == 204

    missing = await client.get("/api/v1/lookups/brands", headers=_auth(meca_token))
    assert not any(b["id"] == brand_id for b in missing.json())


async def test_provider_has_contact_fields(client):
    await _create_user("jefe_lk2@test.com", "Clave123!", UserRole.jefe)
    jefe_token = await _login(client, "jefe_lk2@test.com", "Clave123!")

    created = await client.post(
        "/api/v1/lookups/providers",
        json={
            "name": "Ferretería Central", "contact_name": "Juan Pérez",
            "phone": "+56 9 1234 5678", "email": "contacto@ferreteria.cl",
            "address": "Av. Siempre Viva 742, Santiago",
        },
        headers=_auth(jefe_token),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["contact_name"] == "Juan Pérez"
    assert body["phone"] == "+56 9 1234 5678"
    assert body["email"] == "contacto@ferreteria.cl"
    assert body["address"] == "Av. Siempre Viva 742, Santiago"

    updated = await client.put(
        f"/api/v1/lookups/providers/{body['id']}",
        json={"phone": "+56 9 8765 4321"},
        headers=_auth(jefe_token),
    )
    assert updated.status_code == 200
    assert updated.json()["phone"] == "+56 9 8765 4321"
    assert updated.json()["name"] == "Ferretería Central"  # no se pisa si no viene en el payload
    assert updated.json()["email"] == "contacto@ferreteria.cl"  # tampoco los demás campos
