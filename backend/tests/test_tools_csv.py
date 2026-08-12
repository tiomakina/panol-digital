"""Pruebas de import/export masivo de herramientas por CSV."""
import io

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.tool import Tool, ToolStatus
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


def _csv_file(content: str, filename: str = "herramientas.csv"):
    return {"file": (filename, io.BytesIO(content.encode("utf-8")), "text/csv")}


async def test_export_produces_valid_csv_with_bom(client):
    await _create_user("jefe_csv@test.com", "Clave123!", UserRole.jefe)
    token = await _login(client, "jefe_csv@test.com", "Clave123!")

    await client.post("/api/v1/tools", json={"name": "Taladro CSV", "brand": "Bosch"}, headers=_auth(token))

    res = await client.get("/api/v1/tools/export", headers=_auth(token))
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    body = res.content.decode("utf-8-sig")
    assert "name,brand,model,serial_number" in body
    assert "Taladro CSV" in body


async def test_import_creates_and_updates_and_upserts_lookups(client):
    await _create_user("encargado_csv@test.com", "Clave123!", UserRole.encargado)
    await _create_user("meca_csv@test.com", "Clave123!", UserRole.mecanico)
    encargado_token = await _login(client, "encargado_csv@test.com", "Clave123!")
    mecanico_token = await _login(client, "meca_csv@test.com", "Clave123!")

    # Un mecánico no puede importar
    csv_content = (
        "name,brand,model,serial_number,category,location,supplier,status,purchase_date,"
        "purchase_cost,salvage_value,useful_life_years,depreciation_method,description\n"
        "Amoladora,Makita,GA9020,SN-CSV-001,Eléctricas,Depósito A,Casa Bagnara,disponible,"
        "2024-01-15,50000,5000,5,lineal,Comprada para el taller nuevo\n"
    )
    forbidden = await client.post(
        "/api/v1/tools/import", files=_csv_file(csv_content), headers=_auth(mecanico_token)
    )
    assert forbidden.status_code == 403

    imported = await client.post(
        "/api/v1/tools/import", files=_csv_file(csv_content), headers=_auth(encargado_token)
    )
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert body["created"] == 1
    assert body["updated"] == 0
    assert body["errors"] == []

    listed = await client.get("/api/v1/tools?search=Amoladora", headers=_auth(encargado_token))
    tools = listed.json()
    assert len(tools) == 1
    assert tools[0]["brand"] == "Makita"
    assert tools[0]["serial_number"] == "SN-CSV-001"
    assert tools[0]["status"] == "disponible"

    # La marca y el proveedor nuevos quedaron dados de alta en las tablas maestras
    brands = await client.get("/api/v1/lookups/brands", headers=_auth(encargado_token))
    assert any(b["name"] == "Makita" for b in brands.json())
    providers = await client.get("/api/v1/lookups/providers", headers=_auth(encargado_token))
    assert any(p["name"] == "Casa Bagnara" for p in providers.json())

    # Reimportar el mismo serial actualiza en vez de duplicar, y no toca el status
    # aunque el CSV traiga uno explícito distinto (la fila NO trae status esta vez)
    csv_update = (
        "name,brand,serial_number,description\n"
        "Amoladora Angular Grande,Makita,SN-CSV-001,Descripción actualizada\n"
    )
    reimported = await client.post(
        "/api/v1/tools/import", files=_csv_file(csv_update), headers=_auth(encargado_token)
    )
    assert reimported.status_code == 200, reimported.text
    assert reimported.json()["created"] == 0
    assert reimported.json()["updated"] == 1

    listed_again = await client.get("/api/v1/tools?search=Amoladora", headers=_auth(encargado_token))
    tools_again = listed_again.json()
    assert len(tools_again) == 1
    assert tools_again[0]["name"] == "Amoladora Angular Grande"
    assert tools_again[0]["description"] == "Descripción actualizada"
    assert tools_again[0]["status"] == "disponible"  # no se tocó


async def test_import_rejects_unsafe_status_and_reports_row_errors(client):
    await _create_user("jefe_csv2@test.com", "Clave123!", UserRole.jefe)
    token = await _login(client, "jefe_csv2@test.com", "Clave123!")

    csv_content = (
        "name,status\n"
        "Herramienta Prestada Falsa,prestado\n"
        ",disponible\n"
        "Herramienta OK,disponible\n"
    )
    res = await client.post("/api/v1/tools/import", files=_csv_file(csv_content), headers=_auth(token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["created"] == 1  # solo "Herramienta OK"
    assert len(body["errors"]) == 2
    rows = [e["row"] for e in body["errors"]]
    assert 2 in rows  # status "prestado" no permitido por planilla
    assert 3 in rows  # fila sin nombre


async def test_import_same_serial_twice_in_one_file_does_not_crash(client):
    await _create_user("jefe_csv3@test.com", "Clave123!", UserRole.jefe)
    token = await _login(client, "jefe_csv3@test.com", "Clave123!")

    csv_content = (
        "name,serial_number\n"
        "Primera Version,SN-DUP-1\n"
        "Segunda Version,SN-DUP-1\n"
    )
    res = await client.post("/api/v1/tools/import", files=_csv_file(csv_content), headers=_auth(token))
    assert res.status_code == 200, res.text
    body = res.json()
    # La primera fila crea, la segunda (mismo serial) actualiza esa misma fila
    assert body["created"] == 1
    assert body["updated"] == 1

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(select(Tool).where(Tool.serial_number == "SN-DUP-1"))
        matches = result.scalars().all()
        assert len(matches) == 1
        assert matches[0].name == "Segunda Version"
