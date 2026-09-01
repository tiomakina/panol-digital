"""Pruebas de reportes: inventario, CSV, historial de préstamos y auditoría."""
from datetime import date, timedelta

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


async def test_inventory_report_json_and_csv(client):
    await _create_user("jefe@test.com", "Clave123!", UserRole.jefe)
    token = await _login(client, "jefe@test.com", "Clave123!")

    await client.post(
        "/api/v1/tools",
        json={"name": "Sierra", "purchase_cost": "500.00", "purchase_date": "2024-01-01"},
        headers=_auth(token),
    )

    report = await client.get("/api/v1/reports/inventory", headers=_auth(token))
    assert report.status_code == 200
    body = report.json()
    assert body["total_purchase_cost"] >= 500
    assert any(t["name"] == "Sierra" for t in body["tools"])

    csv_res = await client.get("/api/v1/reports/inventory.csv", headers=_auth(token))
    assert csv_res.status_code == 200
    assert csv_res.headers["content-type"].startswith("text/csv")
    assert "Sierra" in csv_res.text


async def test_inventory_report_includes_location_supplier_and_summary(client):
    await _create_user("jefe_inv@test.com", "Clave123!", UserRole.jefe)
    token = await _login(client, "jefe_inv@test.com", "Clave123!")

    for serial in ("SN-INV-1", "SN-INV-2"):
        await client.post(
            "/api/v1/tools",
            json={
                "name": "Taladro Repetido", "brand": "Bosch", "category": "Eléctricas",
                "location": "Depósito A", "supplier": "Casa Bagnara", "serial_number": serial,
            },
            headers=_auth(token),
        )

    report = await client.get("/api/v1/reports/inventory", headers=_auth(token))
    body = report.json()
    row = next(t for t in body["tools"] if t["serial_number"] == "SN-INV-1")
    assert row["brand"] == "Bosch"
    assert row["location"] == "Depósito A"
    assert row["supplier"] == "Casa Bagnara"

    summary_entry = next(s for s in body["summary"] if s["name"] == "Taladro Repetido")
    assert summary_entry["quantity"] == 2

    csv_res = await client.get("/api/v1/reports/inventory.csv", headers=_auth(token))
    assert "location" in csv_res.text.splitlines()[0]
    assert "Depósito A" in csv_res.text


async def test_loans_report_filters_by_status(client):
    await _create_user("jefe2@test.com", "Clave123!", UserRole.jefe)
    await _create_user("mecanico@test.com", "Clave123!", UserRole.mecanico)
    jefe_token = await _login(client, "jefe2@test.com", "Clave123!")
    mecanico_token = await _login(client, "mecanico@test.com", "Clave123!")

    tool = (await client.post("/api/v1/tools", json={"name": "Pinza"}, headers=_auth(jefe_token))).json()
    borrower_id = (await client.get("/api/v1/auth/me", headers=_auth(mecanico_token))).json()["id"]
    due = (date.today() + timedelta(days=5)).isoformat()

    await client.post(
        "/api/v1/loans",
        json={"tool_id": tool["id"], "borrower_id": borrower_id, "due_date": due},
        headers=_auth(jefe_token),
    )

    active = await client.get("/api/v1/reports/loans", params={"status": "activo"}, headers=_auth(jefe_token))
    assert active.status_code == 200
    assert active.json()["count"] >= 1
    assert active.json()["loans"][0]["tool"] == "Pinza"

    devuelto = await client.get("/api/v1/reports/loans", params={"status": "devuelto"}, headers=_auth(jefe_token))
    assert devuelto.json()["count"] == 0


async def test_loans_report_includes_tool_details_and_summary(client):
    await _create_user("jefe_lr@test.com", "Clave123!", UserRole.jefe)
    await _create_user("meca_lr@test.com", "Clave123!", UserRole.mecanico)
    jefe_token = await _login(client, "jefe_lr@test.com", "Clave123!")
    mecanico_token = await _login(client, "meca_lr@test.com", "Clave123!")

    tool = (await client.post(
        "/api/v1/tools",
        json={"name": "Amoladora Reporte", "brand": "Makita", "category": "Eléctricas", "serial_number": "SN-LR-1"},
        headers=_auth(jefe_token),
    )).json()
    borrower_id = (await client.get("/api/v1/auth/me", headers=_auth(mecanico_token))).json()["id"]
    due = (date.today() + timedelta(days=3)).isoformat()

    await client.post(
        "/api/v1/loans",
        json={"tool_id": tool["id"], "borrower_id": borrower_id, "due_date": due},
        headers=_auth(jefe_token),
    )

    report = await client.get("/api/v1/reports/loans", headers=_auth(jefe_token))
    body = report.json()
    row = next(r for r in body["loans"] if r["tool"] == "Amoladora Reporte")
    assert row["tool_brand"] == "Makita"
    assert row["tool_category"] == "Eléctricas"
    assert row["tool_serial_number"] == "SN-LR-1"

    summary_entry = next(s for s in body["summary"] if s["tool"] == "Amoladora Reporte")
    assert summary_entry["quantity"] == 1


async def test_audit_report_requires_jefe_and_records_actions(client):
    await _create_user("jefe3@test.com", "Clave123!", UserRole.jefe)
    await _create_user("encargado@test.com", "Clave123!", UserRole.encargado)
    jefe_token = await _login(client, "jefe3@test.com", "Clave123!")
    encargado_token = await _login(client, "encargado@test.com", "Clave123!")

    forbidden = await client.get("/api/v1/reports/audit", headers=_auth(encargado_token))
    assert forbidden.status_code == 403

    audit = await client.get("/api/v1/reports/audit", headers=_auth(jefe_token))
    assert audit.status_code == 200
    entries = audit.json()
    actions = [entry["action"] for entry in entries]
    # Los logins de arriba ya debieron quedar registrados
    assert "auth.login" in actions
    # El registro trae quién hizo la acción, no solo el user_id crudo —
    # así el reporte puede mostrar el nombre en vez de un número suelto.
    login_entry = next(e for e in entries if e["action"] == "auth.login")
    assert login_entry["user"] is not None
    assert login_entry["user"]["full_name"]


async def test_audit_report_resolves_entity_label_for_user_photo_update(client):
    """
    Bug reportado: la columna Entidad del reporte de auditoría mostraba
    solo "user #1" — sin nombre, no servía para saber de quién era la
    foto que se cambió. Ahora el reporte resuelve un nombre legible para
    las entidades que sí se auditan (user/tool/toolbox).
    """
    await _create_user("jefe4@test.com", "Clave123!", UserRole.jefe)
    jefe_token = await _login(client, "jefe4@test.com", "Clave123!")
    jefe_id = (await client.get("/api/v1/auth/me", headers=_auth(jefe_token))).json()["id"]

    photo = await client.post(
        f"/api/v1/users/{jefe_id}/photo",
        files={"file": ("foto.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 32, "image/png")},
        headers=_auth(jefe_token),
    )
    assert photo.status_code == 200, photo.text

    audit = await client.get("/api/v1/reports/audit", headers=_auth(jefe_token))
    assert audit.status_code == 200
    entry = next(e for e in audit.json() if e["action"] == "user.photo_update")
    assert entry["entity_type"] == "user"
    assert entry["entity_id"] == jefe_id
    assert entry["entity_label"] == "Seed"  # full_name del usuario creado por _create_user
