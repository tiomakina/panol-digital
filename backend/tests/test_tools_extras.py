"""
Pruebas de las mejoras a Herramientas pedidas después de las primeras
pruebas del cliente: ocultar valores económicos a no-Jefe, CSV de
ejemplo, código de producto, y documento de compra (folio + adjunto).
"""
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


def _fake_pdf() -> bytes:
    return b"%PDF-1.4\n" + b"\x00" * 32


def _fake_png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


async def test_economic_values_hidden_from_non_jefe(client):
    await _create_user("jefe_val@test.com", "Clave123!", UserRole.jefe)
    await _create_user("meca_val@test.com", "Clave123!", UserRole.mecanico)
    jefe_token = await _login(client, "jefe_val@test.com", "Clave123!")
    meca_token = await _login(client, "meca_val@test.com", "Clave123!")

    created = await client.post(
        "/api/v1/tools",
        json={
            "name": "Taladro Valioso", "purchase_cost": "100000", "salvage_value": "10000",
            "purchase_date": "2024-01-01",
        },
        headers=_auth(jefe_token),
    )
    assert created.status_code == 201, created.text
    tool_id = created.json()["id"]
    # El Jefe que lo crea sí ve los valores en la respuesta
    assert created.json()["purchase_cost"] == "100000.00"
    assert created.json()["current_value"] is not None

    # Un Mecánico consultando la MISMA herramienta no ve nada de plata
    as_meca = await client.get(f"/api/v1/tools/{tool_id}", headers=_auth(meca_token))
    assert as_meca.status_code == 200
    body = as_meca.json()
    assert body["purchase_cost"] is None
    assert body["salvage_value"] is None
    assert body["current_value"] is None
    # El resto de los datos sigue visible normalmente
    assert body["name"] == "Taladro Valioso"

    # Tampoco en el listado
    listing = await client.get("/api/v1/tools", headers=_auth(meca_token))
    row = next(t for t in listing.json() if t["id"] == tool_id)
    assert row["purchase_cost"] is None
    assert row["current_value"] is None

    # El Jefe sigue viendo los valores en el listado
    listing_jefe = await client.get("/api/v1/tools", headers=_auth(jefe_token))
    row_jefe = next(t for t in listing_jefe.json() if t["id"] == tool_id)
    assert row_jefe["purchase_cost"] == "100000.00"


async def test_download_example_csv(client):
    await _create_user("meca_ex@test.com", "Clave123!", UserRole.mecanico)
    token = await _login(client, "meca_ex@test.com", "Clave123!")

    res = await client.get("/api/v1/tools/import/example", headers=_auth(token))
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    body = res.content.decode("utf-8-sig")
    assert "name,product_code,brand" in body
    assert "Taladro Percutor" in body  # fila de ejemplo


async def test_product_code_and_multiple_serials(client):
    """
    El código de producto identifica el modelo, no la unidad — dos
    herramientas pueden compartir product_code con distinto serial_number
    (esto es lo que habilita "duplicar herramienta" desde la UI).
    """
    await _create_user("encargado_pc@test.com", "Clave123!", UserRole.encargado)
    token = await _login(client, "encargado_pc@test.com", "Clave123!")

    unit1 = await client.post(
        "/api/v1/tools",
        json={"name": "Amoladora", "product_code": "AMO-MAKITA-9020", "serial_number": "SN-A"},
        headers=_auth(token),
    )
    assert unit1.status_code == 201
    unit2 = await client.post(
        "/api/v1/tools",
        json={"name": "Amoladora", "product_code": "AMO-MAKITA-9020", "serial_number": "SN-B"},
        headers=_auth(token),
    )
    assert unit2.status_code == 201, unit2.text
    assert unit1.json()["product_code"] == unit2.json()["product_code"]
    assert unit1.json()["serial_number"] != unit2.json()["serial_number"]

    # El número de serie sigue siendo único (eso no cambia)
    dup_serial = await client.post(
        "/api/v1/tools",
        json={"name": "Otra", "product_code": "AMO-MAKITA-9020", "serial_number": "SN-A"},
        headers=_auth(token),
    )
    assert dup_serial.status_code == 400


async def test_purchase_document_folio_and_upload(client):
    await _create_user("encargado_doc@test.com", "Clave123!", UserRole.encargado)
    token = await _login(client, "encargado_doc@test.com", "Clave123!")

    created = await client.post(
        "/api/v1/tools",
        json={"name": "Sierra", "purchase_document_folio": "F-00123"},
        headers=_auth(token),
    )
    tool_id = created.json()["id"]
    assert created.json()["purchase_document_folio"] == "F-00123"

    uploaded = await client.post(
        f"/api/v1/tools/{tool_id}/purchase-document",
        files={"file": ("factura.pdf", _fake_pdf(), "application/pdf")},
        headers=_auth(token),
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["purchase_document_url"].startswith("/static/uploads/purchase_docs/")

    # También acepta imagen
    uploaded_img = await client.post(
        f"/api/v1/tools/{tool_id}/purchase-document",
        files={"file": ("boleta.png", _fake_png(), "image/png")},
        headers=_auth(token),
    )
    assert uploaded_img.status_code == 200


async def test_provider_rut(client):
    await _create_user("jefe_rut@test.com", "Clave123!", UserRole.jefe)
    token = await _login(client, "jefe_rut@test.com", "Clave123!")

    created = await client.post(
        "/api/v1/lookups/providers",
        json={"name": "Proveedor RUT", "rut": "76.123.456-7"},
        headers=_auth(token),
    )
    assert created.status_code == 201, created.text
    assert created.json()["rut"] == "76.123.456-7"
