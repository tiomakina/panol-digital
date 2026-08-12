"""Pruebas de integración: CRUD de herramientas, flujo de préstamos y KPIs del dashboard."""
from datetime import date, timedelta

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole


async def _create_user(email: str, password: str, role: UserRole) -> None:
    async with AsyncSessionLocal() as db:
        db.add(User(email=email, full_name="Test", role=role, hashed_password=hash_password(password)))
        await db.commit()


async def _login(client, email, password) -> str:
    res = await client.post("/api/v1/auth/login", data={"username": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _user_id(client, token: str) -> int:
    res = await client.get("/api/v1/auth/me", headers=_auth(token))
    return res.json()["id"]


async def test_tool_lifecycle_and_loan_flow(client):
    await _create_user("jefe1@test.com", "Clave123!", UserRole.jefe)
    await _create_user("mecanico1@test.com", "Clave123!", UserRole.mecanico)

    jefe_token = await _login(client, "jefe1@test.com", "Clave123!")
    mecanico_token = await _login(client, "mecanico1@test.com", "Clave123!")

    # Un mecánico no puede crear herramientas (requiere rol encargado+)
    forbidden = await client.post("/api/v1/tools", json={"name": "Taladro"}, headers=_auth(mecanico_token))
    assert forbidden.status_code == 403

    # El jefe sí puede, y se genera el QR automáticamente
    created = await client.post(
        "/api/v1/tools",
        json={
            "name": "Taladro Percutor",
            "brand": "Bosch",
            "serial_number": "SN-001",
            "purchase_cost": "1000.00",
            "salvage_value": "100.00",
            "useful_life_years": 5,
            "purchase_date": "2024-01-01",
        },
        headers=_auth(jefe_token),
    )
    assert created.status_code == 201, created.text
    tool = created.json()
    assert tool["status"] == "disponible"
    assert tool["qr_code_url"]
    assert tool["current_value"] is not None
    tool_id = tool["id"]

    # No se puede repetir el número de serie
    dup = await client.post(
        "/api/v1/tools", json={"name": "Otra", "serial_number": "SN-001"}, headers=_auth(jefe_token)
    )
    assert dup.status_code == 400

    # Búsqueda en el listado
    listing = await client.get("/api/v1/tools", params={"search": "Taladro"}, headers=_auth(mecanico_token))
    assert listing.status_code == 200
    assert any(t["id"] == tool_id for t in listing.json())

    # Registrar un préstamo
    due = (date.today() + timedelta(days=7)).isoformat()
    borrower_id = await _user_id(client, mecanico_token)
    loan_res = await client.post(
        "/api/v1/loans",
        json={"tool_id": tool_id, "borrower_id": borrower_id, "due_date": due, "purpose": "Obra"},
        headers=_auth(jefe_token),
    )
    assert loan_res.status_code == 201, loan_res.text
    loan = loan_res.json()
    assert loan["status"] == "activo"
    loan_id = loan["id"]

    # La herramienta pasa a "prestado"
    tool_after = (await client.get(f"/api/v1/tools/{tool_id}", headers=_auth(mecanico_token))).json()
    assert tool_after["status"] == "prestado"

    # No se puede volver a prestar mientras está prestada
    again = await client.post(
        "/api/v1/loans",
        json={"tool_id": tool_id, "borrower_id": borrower_id, "due_date": due},
        headers=_auth(jefe_token),
    )
    assert again.status_code == 400

    # Descargar el vale PDF
    voucher = await client.get(f"/api/v1/loans/{loan_id}/voucher", headers=_auth(mecanico_token))
    assert voucher.status_code == 200
    assert voucher.headers["content-type"] == "application/pdf"

    # Devolver la herramienta en buen estado
    returned = await client.post(
        f"/api/v1/loans/{loan_id}/return",
        json={"return_condition": "bueno"},
        headers=_auth(jefe_token),
    )
    assert returned.status_code == 200
    assert returned.json()["status"] == "devuelto"

    tool_final = (await client.get(f"/api/v1/tools/{tool_id}", headers=_auth(mecanico_token))).json()
    assert tool_final["status"] == "disponible"

    # KPIs del dashboard reflejan el inventario
    kpis = await client.get("/api/v1/dashboard/kpis", headers=_auth(mecanico_token))
    assert kpis.status_code == 200
    assert kpis.json()["total_tools"] >= 1


async def test_loan_lost_marks_tool_as_baja(client):
    await _create_user("jefe2@test.com", "Clave123!", UserRole.jefe)
    await _create_user("mecanico2@test.com", "Clave123!", UserRole.mecanico)
    jefe_token = await _login(client, "jefe2@test.com", "Clave123!")
    mecanico_token = await _login(client, "mecanico2@test.com", "Clave123!")

    tool = (await client.post(
        "/api/v1/tools", json={"name": "Amoladora", "serial_number": "SN-999"}, headers=_auth(jefe_token)
    )).json()

    due = (date.today() + timedelta(days=3)).isoformat()
    borrower_id = await _user_id(client, mecanico_token)
    loan = (await client.post(
        "/api/v1/loans",
        json={"tool_id": tool["id"], "borrower_id": borrower_id, "due_date": due},
        headers=_auth(jefe_token),
    )).json()

    returned = await client.post(
        f"/api/v1/loans/{loan['id']}/return",
        json={"return_condition": "perdido"},
        headers=_auth(jefe_token),
    )
    assert returned.status_code == 200
    assert returned.json()["status"] == "extraviado"

    tool_final = (await client.get(f"/api/v1/tools/{tool['id']}", headers=_auth(mecanico_token))).json()
    assert tool_final["status"] == "baja"
