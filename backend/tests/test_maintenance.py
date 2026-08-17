"""Pruebas del módulo de mantenimiento y de la baja de herramientas."""
from datetime import date

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.loan import Loan, LoanStatus
from app.models.tool import Tool, ToolStatus
from app.models.toolbox import Toolbox, ToolboxItem
from app.models.user import User, UserRole
from rut_test_helper import fake_rut


async def _create_user(email: str, password: str, role: UserRole, full_name: str = "Test") -> int:
    async with AsyncSessionLocal() as db:
        user = User(email=email, rut=fake_rut(email), full_name=full_name, role=role, hashed_password=hash_password(password))
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.id


async def _login(client, email, password) -> str:
    res = await client.post("/api/v1/auth/login", data={"username": fake_rut(email), "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_send_to_maintenance_removes_from_toolbox_and_updates_status(client):
    await _create_user("jefe_mt@test.com", "Clave123!", UserRole.jefe)
    jefe_token = await _login(client, "jefe_mt@test.com", "Clave123!")

    async with AsyncSessionLocal() as db:
        tool = Tool(name="Amoladora", status=ToolStatus.en_caja)
        toolbox = Toolbox(name="Caja QA")
        db.add_all([tool, toolbox])
        await db.flush()
        db.add(ToolboxItem(toolbox_id=toolbox.id, tool_id=tool.id))
        await db.commit()
        tool_id, toolbox_id = tool.id, toolbox.id

    sent = await client.post(
        "/api/v1/maintenance",
        json={"tool_id": tool_id, "provider": "Taller Central", "reason": "Ruido en el motor"},
        headers=_auth(jefe_token),
    )
    assert sent.status_code == 201, sent.text
    record = sent.json()
    assert record["status"] == "en_proceso"
    assert record["provider"] == "Taller Central"

    tool_check = await client.get(f"/api/v1/tools/{tool_id}", headers=_auth(jefe_token))
    assert tool_check.json()["status"] == "mantenimiento"

    box_check = await client.get(f"/api/v1/toolboxes/{toolbox_id}", headers=_auth(jefe_token))
    assert box_check.json()["items"] == []

    # No se puede volver a mandar a mantenimiento mientras ya está en mantenimiento
    again = await client.post(
        "/api/v1/maintenance",
        json={"tool_id": tool_id, "reason": "otra vez"},
        headers=_auth(jefe_token),
    )
    assert again.status_code == 400


async def test_resolve_maintenance_resuelto_vs_sin_solucion(client):
    await _create_user("jefe_mt2@test.com", "Clave123!", UserRole.jefe)
    jefe_token = await _login(client, "jefe_mt2@test.com", "Clave123!")

    async with AsyncSessionLocal() as db:
        tool = Tool(name="Sierra", status=ToolStatus.disponible)
        db.add(tool)
        await db.commit()
        await db.refresh(tool)
        tool_id = tool.id

    sent = await client.post(
        "/api/v1/maintenance", json={"tool_id": tool_id, "reason": "no enciende"}, headers=_auth(jefe_token)
    )
    record_id = sent.json()["id"]

    resolved = await client.post(
        f"/api/v1/maintenance/{record_id}/resolve",
        json={"status": "resuelto", "resolution_notes": "Se cambió el cable"},
        headers=_auth(jefe_token),
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "resuelto"

    tool_check = await client.get(f"/api/v1/tools/{tool_id}", headers=_auth(jefe_token))
    assert tool_check.json()["status"] == "disponible"

    # No se puede resolver de nuevo un registro ya cerrado
    again = await client.post(
        f"/api/v1/maintenance/{record_id}/resolve",
        json={"status": "resuelto"},
        headers=_auth(jefe_token),
    )
    assert again.status_code == 400


async def test_sin_solucion_stays_in_maintenance_until_decommissioned(client):
    await _create_user("jefe_mt3@test.com", "Clave123!", UserRole.jefe)
    jefe_token = await _login(client, "jefe_mt3@test.com", "Clave123!")
    authorizer_id = await _create_user("gerente@test.com", "Clave123!", UserRole.jefe, "Gerente General")

    async with AsyncSessionLocal() as db:
        tool = Tool(name="Compresor", status=ToolStatus.disponible)
        db.add(tool)
        await db.commit()
        await db.refresh(tool)
        tool_id = tool.id

    sent = await client.post(
        "/api/v1/maintenance", json={"tool_id": tool_id, "reason": "motor quemado"}, headers=_auth(jefe_token)
    )
    record_id = sent.json()["id"]

    resolved = await client.post(
        f"/api/v1/maintenance/{record_id}/resolve",
        json={"status": "sin_solucion", "resolution_notes": "No es reparable"},
        headers=_auth(jefe_token),
    )
    assert resolved.status_code == 200

    # La herramienta se queda en "mantenimiento" — no se da de baja sola
    tool_check = await client.get(f"/api/v1/tools/{tool_id}", headers=_auth(jefe_token))
    assert tool_check.json()["status"] == "mantenimiento"

    decommissioned = await client.post(
        f"/api/v1/tools/{tool_id}/decommission",
        json={"reason": "Motor quemado sin reparación posible", "authorized_by_id": authorizer_id},
        headers=_auth(jefe_token),
    )
    assert decommissioned.status_code == 200, decommissioned.text
    body = decommissioned.json()
    assert body["status"] == "baja"
    assert body["decommission_reason"] == "Motor quemado sin reparación posible"
    assert body["decommission_authorized_by"]["full_name"] == "Gerente General"


async def test_decommission_requires_jefe_and_blocks_loaned_tools(client):
    await _create_user("encargado_mt@test.com", "Clave123!", UserRole.encargado)
    await _create_user("meca_mt@test.com", "Clave123!", UserRole.mecanico)
    encargado_token = await _login(client, "encargado_mt@test.com", "Clave123!")

    async with AsyncSessionLocal() as db:
        tool = Tool(name="Nivel", status=ToolStatus.prestado)
        db.add(tool)
        await db.commit()
        await db.refresh(tool)
        tool_id = tool.id

    # Un encargado no alcanza — dar de baja requiere jefe
    forbidden = await client.post(
        f"/api/v1/tools/{tool_id}/decommission",
        json={"reason": "x", "authorized_by_id": 1},
        headers=_auth(encargado_token),
    )
    assert forbidden.status_code == 403


async def test_damaged_return_creates_maintenance_record(client):
    """
    Si se devuelve una herramienta dañada o a reparación, tiene que quedar
    un registro en el módulo de mantenimiento — no alcanza con solo
    cambiarle el status a la herramienta (si no, queda "mantenimiento"
    sin nada que lo explique).
    """
    jefe_id = await _create_user("jefe_mt4@test.com", "Clave123!", UserRole.jefe)
    mecanico_id = await _create_user("meca_mt4@test.com", "Clave123!", UserRole.mecanico)
    jefe_token = await _login(client, "jefe_mt4@test.com", "Clave123!")

    async with AsyncSessionLocal() as db:
        tool = Tool(name="Rotomartillo", status=ToolStatus.prestado)
        db.add(tool)
        await db.flush()
        loan = Loan(
            tool_id=tool.id, borrower_id=mecanico_id, issued_by_id=jefe_id,
            due_date=date.today(), status=LoanStatus.activo,
        )
        db.add(loan)
        await db.commit()
        await db.refresh(tool)
        await db.refresh(loan)
        tool_id, loan_id = tool.id, loan.id

    returned = await client.post(
        f"/api/v1/loans/{loan_id}/return",
        json={"return_condition": "reparacion", "notes": "Hace ruido raro"},
        headers=_auth(jefe_token),
    )
    assert returned.status_code == 200, returned.text

    tool_check = await client.get(f"/api/v1/tools/{tool_id}", headers=_auth(jefe_token))
    assert tool_check.json()["status"] == "mantenimiento"

    records = await client.get(f"/api/v1/maintenance?tool_id={tool_id}", headers=_auth(jefe_token))
    assert records.status_code == 200
    body = records.json()
    assert len(body) == 1
    assert "reparación" in body[0]["reason"] or str(loan_id) in body[0]["reason"]
    assert "Hace ruido raro" in body[0]["reason"]


def _fake_png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _fake_pdf() -> bytes:
    # Header real de PDF (magic bytes) — no hace falta un PDF válido entero
    # para pasar la validación de tipo real de archivo.
    return b"%PDF-1.4\n" + b"\x00" * 32


async def _send_tool_to_maintenance(client, token: str, tool_name: str = "Multímetro") -> tuple[int, int]:
    async with AsyncSessionLocal() as db:
        tool = Tool(name=tool_name, status=ToolStatus.disponible)
        db.add(tool)
        await db.commit()
        await db.refresh(tool)
        tool_id = tool.id

    sent = await client.post(
        "/api/v1/maintenance", json={"tool_id": tool_id, "reason": "en revisión"}, headers=_auth(token)
    )
    assert sent.status_code == 201, sent.text
    return tool_id, sent.json()["id"]


async def test_upload_multiple_documents_image_and_pdf(client):
    """
    Un mismo registro tiene que poder acumular varios comprobantes (antes
    la segunda subida pisaba a la primera), y aceptar tanto imagen como PDF.
    """
    await _create_user("encargado_doc@test.com", "Clave123!", UserRole.encargado)
    token = await _login(client, "encargado_doc@test.com", "Clave123!")
    _, record_id = await _send_tool_to_maintenance(client, token)

    up1 = await client.post(
        f"/api/v1/maintenance/{record_id}/document",
        files={"file": ("cotizacion.png", _fake_png(), "image/png")},
        headers=_auth(token),
    )
    assert up1.status_code == 200, up1.text
    assert len(up1.json()["documents"]) == 1
    assert up1.json()["documents"][0]["mime_type"] == "image/png"

    up2 = await client.post(
        f"/api/v1/maintenance/{record_id}/document",
        files={"file": ("orden_trabajo.pdf", _fake_pdf(), "application/pdf")},
        headers=_auth(token),
    )
    assert up2.status_code == 200, up2.text
    docs = up2.json()["documents"]
    assert len(docs) == 2  # la segunda subida se SUMA, no reemplaza a la primera
    mimes = {d["mime_type"] for d in docs}
    assert mimes == {"image/png", "application/pdf"}
    for d in docs:
        assert d["file_url"].startswith("/static/uploads/maintenance/")


async def test_reject_invalid_document_file(client):
    await _create_user("encargado_doc2@test.com", "Clave123!", UserRole.encargado)
    token = await _login(client, "encargado_doc2@test.com", "Clave123!")
    _, record_id = await _send_tool_to_maintenance(client, token)

    bad = await client.post(
        f"/api/v1/maintenance/{record_id}/document",
        files={"file": ("virus.exe", b"MZ\x90\x00" + b"\x00" * 32, "application/octet-stream")},
        headers=_auth(token),
    )
    assert bad.status_code == 400


async def test_mecanico_cannot_upload_or_delete_documents(client):
    await _create_user("encargado_doc3@test.com", "Clave123!", UserRole.encargado)
    await _create_user("meca_doc@test.com", "Clave123!", UserRole.mecanico)
    encargado_token = await _login(client, "encargado_doc3@test.com", "Clave123!")
    meca_token = await _login(client, "meca_doc@test.com", "Clave123!")
    _, record_id = await _send_tool_to_maintenance(client, encargado_token)

    forbidden_upload = await client.post(
        f"/api/v1/maintenance/{record_id}/document",
        files={"file": ("foto.png", _fake_png(), "image/png")},
        headers=_auth(meca_token),
    )
    assert forbidden_upload.status_code == 403

    forbidden_delete = await client.delete(
        f"/api/v1/maintenance/{record_id}/document/1", headers=_auth(meca_token)
    )
    assert forbidden_delete.status_code == 403


async def test_delete_maintenance_document(client):
    await _create_user("encargado_doc4@test.com", "Clave123!", UserRole.encargado)
    token = await _login(client, "encargado_doc4@test.com", "Clave123!")
    _, record_id = await _send_tool_to_maintenance(client, token)

    uploaded = await client.post(
        f"/api/v1/maintenance/{record_id}/document",
        files={"file": ("foto.png", _fake_png(), "image/png")},
        headers=_auth(token),
    )
    doc_id = uploaded.json()["documents"][0]["id"]

    deleted = await client.delete(f"/api/v1/maintenance/{record_id}/document/{doc_id}", headers=_auth(token))
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["documents"] == []

    not_found = await client.delete(f"/api/v1/maintenance/{record_id}/document/{doc_id}", headers=_auth(token))
    assert not_found.status_code == 404


async def test_document_title_and_note(client):
    await _create_user("encargado_doc5@test.com", "Clave123!", UserRole.encargado)
    token = await _login(client, "encargado_doc5@test.com", "Clave123!")
    _, record_id = await _send_tool_to_maintenance(client, token)

    uploaded = await client.post(
        f"/api/v1/maintenance/{record_id}/document",
        files={"file": ("cotizacion.pdf", _fake_pdf(), "application/pdf")},
        data={"title": "Cotización taller", "note": "Incluye repuestos e IVA"},
        headers=_auth(token),
    )
    assert uploaded.status_code == 200, uploaded.text
    doc = uploaded.json()["documents"][0]
    assert doc["title"] == "Cotización taller"
    assert doc["note"] == "Incluye repuestos e IVA"

    # Se puede subir sin título/observación (quedan en null, no es obligatorio)
    uploaded_bare = await client.post(
        f"/api/v1/maintenance/{record_id}/document",
        files={"file": ("otro.png", _fake_png(), "image/png")},
        headers=_auth(token),
    )
    assert uploaded_bare.status_code == 200
    docs = uploaded_bare.json()["documents"]
    assert any(d["title"] is None for d in docs)

    # Corregir el título/observación de un documento ya subido
    doc_id = doc["id"]
    edited = await client.put(
        f"/api/v1/maintenance/{record_id}/document/{doc_id}",
        json={"title": "Cotización taller (corregida)"},
        headers=_auth(token),
    )
    assert edited.status_code == 200, edited.text
    edited_doc = next(d for d in edited.json()["documents"] if d["id"] == doc_id)
    assert edited_doc["title"] == "Cotización taller (corregida)"
    assert edited_doc["note"] == "Incluye repuestos e IVA"  # no se pisó al no venir en el payload
