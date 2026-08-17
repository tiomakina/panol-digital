"""
Pruebas de la revisión de permisos por rol pedida por el cliente: qué ve y
qué puede hacer cada uno (Jefe / Encargado / Mecánico) en cada módulo,
además del flujo nuevo de "solicitar mantención" desde Cajas.
"""
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.tool import Tool, ToolStatus
from app.models.toolbox import Toolbox, ToolboxItem
from app.models.user import User, UserRole


async def _create_user(email: str, password: str, role: UserRole) -> int:
    async with AsyncSessionLocal() as db:
        user = User(email=email, full_name="Seed", role=role, hashed_password=hash_password(password))
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.id


async def _login(client, email, password) -> str:
    res = await client.post("/api/v1/auth/login", data={"username": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Dashboard: valor de inventario solo para Jefe -------------------------

async def test_dashboard_inventory_value_hidden_from_non_jefe(client):
    await _create_user("jefe_kpi2@test.com", "Clave123!", UserRole.jefe)
    await _create_user("enc_kpi2@test.com", "Clave123!", UserRole.encargado)
    await _create_user("meca_kpi2@test.com", "Clave123!", UserRole.mecanico)
    jefe_token = await _login(client, "jefe_kpi2@test.com", "Clave123!")
    encargado_token = await _login(client, "enc_kpi2@test.com", "Clave123!")
    mecanico_token = await _login(client, "meca_kpi2@test.com", "Clave123!")

    await client.post(
        "/api/v1/tools",
        json={"name": "Herramienta Valiosa", "purchase_cost": "10000", "purchase_date": "2024-01-01"},
        headers=_auth(jefe_token),
    )

    jefe_kpis = (await client.get("/api/v1/dashboard/kpis", headers=_auth(jefe_token))).json()
    assert jefe_kpis["inventory_value"] is not None

    for token in (encargado_token, mecanico_token):
        kpis = (await client.get("/api/v1/dashboard/kpis", headers=_auth(token))).json()
        assert kpis["inventory_value"] is None


# --- Herramientas: exportar bloqueado para Mecánico + costos enmascarados --

async def test_export_blocked_for_mecanico_and_masked_for_encargado(client):
    await _create_user("jefe_exp@test.com", "Clave123!", UserRole.jefe)
    await _create_user("enc_exp@test.com", "Clave123!", UserRole.encargado)
    await _create_user("meca_exp@test.com", "Clave123!", UserRole.mecanico)
    jefe_token = await _login(client, "jefe_exp@test.com", "Clave123!")
    encargado_token = await _login(client, "enc_exp@test.com", "Clave123!")
    mecanico_token = await _login(client, "meca_exp@test.com", "Clave123!")

    await client.post(
        "/api/v1/tools",
        json={"name": "Taladro Export", "purchase_cost": "77000", "salvage_value": "7000"},
        headers=_auth(jefe_token),
    )

    forbidden = await client.get("/api/v1/tools/export", headers=_auth(mecanico_token))
    assert forbidden.status_code == 403

    jefe_csv = (await client.get("/api/v1/tools/export", headers=_auth(jefe_token))).text
    assert "77000" in jefe_csv

    # Encargado puede exportar, pero sin los valores económicos — si no,
    # exportar era una forma de esquivar el enmascarado que ya aplica la
    # API JSON.
    encargado_csv = (await client.get("/api/v1/tools/export", headers=_auth(encargado_token))).text
    assert "Taladro Export" in encargado_csv
    assert "77000" not in encargado_csv


# --- Préstamos: Mecánico solo ve su propio vale -----------------------------

async def test_mecanico_can_only_download_own_voucher(client):
    jefe_id = await _create_user("jefe_voucher@test.com", "Clave123!", UserRole.jefe)
    meca_a_id = await _create_user("meca_voucher_a@test.com", "Clave123!", UserRole.mecanico)
    await _create_user("meca_voucher_b@test.com", "Clave123!", UserRole.mecanico)
    jefe_token = await _login(client, "jefe_voucher@test.com", "Clave123!")
    meca_a_token = await _login(client, "meca_voucher_a@test.com", "Clave123!")
    meca_b_token = await _login(client, "meca_voucher_b@test.com", "Clave123!")

    async with AsyncSessionLocal() as db:
        from datetime import date, timedelta

        from app.models.loan import Loan, LoanStatus

        tool = Tool(name="Sierra Voucher", status=ToolStatus.prestado)
        db.add(tool)
        await db.flush()
        loan = Loan(
            tool_id=tool.id, borrower_id=meca_a_id, issued_by_id=jefe_id,
            due_date=date.today() + timedelta(days=5), status=LoanStatus.activo,
        )
        db.add(loan)
        await db.commit()
        await db.refresh(loan)
        loan_id = loan.id

    own = await client.get(f"/api/v1/loans/{loan_id}/voucher", headers=_auth(meca_a_token))
    assert own.status_code == 200

    other = await client.get(f"/api/v1/loans/{loan_id}/voucher", headers=_auth(meca_b_token))
    assert other.status_code == 403

    jefe_access = await client.get(f"/api/v1/loans/{loan_id}/voucher", headers=_auth(jefe_token))
    assert jefe_access.status_code == 200


async def test_loan_response_embeds_tool_and_borrower_names(client):
    """
    Bug reportado: la columna "Responsable" mostraba "Usuario #<id>" en vez
    del nombre porque el frontend resolvía el nombre con una lista de
    usuarios que un Mecánico no puede cargar (GET /users es Encargado+).
    La API ahora manda el nombre embebido directo en el préstamo.
    """
    await _create_user("jefe_embed@test.com", "Clave123!", UserRole.jefe)
    jefe_token = await _login(client, "jefe_embed@test.com", "Clave123!")
    borrower_id = await _create_user("meca_embed@test.com", "Clave123!", UserRole.mecanico)

    tool = (await client.post(
        "/api/v1/tools", json={"name": "Nivel Embed"}, headers=_auth(jefe_token)
    )).json()
    from datetime import date, timedelta

    await client.post(
        "/api/v1/loans",
        json={
            "tool_id": tool["id"], "borrower_id": borrower_id,
            "due_date": (date.today() + timedelta(days=2)).isoformat(),
        },
        headers=_auth(jefe_token),
    )

    listing = await client.get("/api/v1/loans", headers=_auth(jefe_token))
    loan = next(l for l in listing.json() if l["tool_id"] == tool["id"])
    assert loan["tool"]["name"] == "Nivel Embed"
    assert loan["borrower"]["full_name"] == "Seed"


# --- Cajas: Mecánico ve solo la suya, y solicita mantención -----------------

async def test_mecanico_sees_only_own_toolbox(client):
    await _create_user("jefe_box@test.com", "Clave123!", UserRole.jefe)
    jefe_token = await _login(client, "jefe_box@test.com", "Clave123!")
    meca_id = await _create_user("meca_box@test.com", "Clave123!", UserRole.mecanico)
    await _create_user("meca_box2@test.com", "Clave123!", UserRole.mecanico)
    meca_token = await _login(client, "meca_box@test.com", "Clave123!")
    meca2_token = await _login(client, "meca_box2@test.com", "Clave123!")

    own_box = (await client.post(
        "/api/v1/toolboxes",
        json={"name": "Caja de Meca", "responsible_user_id": meca_id},
        headers=_auth(jefe_token),
    )).json()
    await client.post(
        "/api/v1/toolboxes", json={"name": "Caja Ajena"}, headers=_auth(jefe_token)
    )

    listing = await client.get("/api/v1/toolboxes", headers=_auth(meca_token))
    assert [b["name"] for b in listing.json()] == ["Caja de Meca"]

    # Y no puede ver el detalle de la que no es suya
    other_boxes = await client.get("/api/v1/toolboxes", headers=_auth(jefe_token))
    other_id = next(b["id"] for b in other_boxes.json() if b["name"] == "Caja Ajena")
    forbidden = await client.get(f"/api/v1/toolboxes/{other_id}", headers=_auth(meca_token))
    assert forbidden.status_code == 403

    # Otro Mecánico tampoco puede ver la caja del primero
    forbidden2 = await client.get(f"/api/v1/toolboxes/{own_box['id']}", headers=_auth(meca2_token))
    assert forbidden2.status_code == 403


async def test_mecanico_requests_maintenance_and_encargado_confirms(client):
    await _create_user("jefe_req@test.com", "Clave123!", UserRole.jefe)
    jefe_token = await _login(client, "jefe_req@test.com", "Clave123!")
    meca_id = await _create_user("meca_req@test.com", "Clave123!", UserRole.mecanico)
    meca_token = await _login(client, "meca_req@test.com", "Clave123!")
    await _create_user("enc_req@test.com", "Clave123!", UserRole.encargado)
    encargado_token = await _login(client, "enc_req@test.com", "Clave123!")

    async with AsyncSessionLocal() as db:
        toolbox = Toolbox(name="Caja Solicitud", responsible_user_id=meca_id)
        tool = Tool(name="Rotomartillo Solicitud", status=ToolStatus.en_caja)
        db.add_all([toolbox, tool])
        await db.flush()
        db.add(ToolboxItem(toolbox_id=toolbox.id, tool_id=tool.id))
        await db.commit()
        toolbox_id, tool_id = toolbox.id, tool.id

    requested = await client.post(
        f"/api/v1/toolboxes/{toolbox_id}/tools/{tool_id}/request-maintenance",
        json={"reason": "No enciende"},
        headers=_auth(meca_token),
    )
    assert requested.status_code == 200, requested.text
    item = next(i for i in requested.json()["items"] if i["tool_id"] == tool_id)
    assert item["tool"]["status"] == "mantenimiento_solicitada"
    assert item["tool"]["maintenance_requested_by"]["full_name"] == "Seed"
    assert item["tool"]["maintenance_requested_reason"] == "No enciende"

    # No se puede solicitar dos veces mientras sigue pendiente
    again = await client.post(
        f"/api/v1/toolboxes/{toolbox_id}/tools/{tool_id}/request-maintenance",
        json={"reason": "otra vez"},
        headers=_auth(meca_token),
    )
    assert again.status_code == 400

    # Un Encargado confirma la solicitud desde el flujo normal de
    # mantenimiento — tiene que poder partir de "mantenimiento_solicitada"
    confirmed = await client.post(
        "/api/v1/maintenance",
        json={"tool_id": tool_id, "provider": "Taller Central", "reason": "Diagnóstico inicial"},
        headers=_auth(encargado_token),
    )
    assert confirmed.status_code == 201, confirmed.text

    tool_check = await client.get(f"/api/v1/tools/{tool_id}", headers=_auth(jefe_token))
    assert tool_check.json()["status"] == "mantenimiento"


async def test_mecanico_cannot_request_maintenance_for_other_toolbox(client):
    await _create_user("jefe_req2@test.com", "Clave123!", UserRole.jefe)
    jefe_token = await _login(client, "jefe_req2@test.com", "Clave123!")
    await _create_user("meca_req2@test.com", "Clave123!", UserRole.mecanico)
    meca_token = await _login(client, "meca_req2@test.com", "Clave123!")

    async with AsyncSessionLocal() as db:
        toolbox = Toolbox(name="Caja Sin Asignar")  # responsible_user_id=None
        tool = Tool(name="Herramienta Sin Asignar", status=ToolStatus.en_caja)
        db.add_all([toolbox, tool])
        await db.flush()
        db.add(ToolboxItem(toolbox_id=toolbox.id, tool_id=tool.id))
        await db.commit()
        toolbox_id, tool_id = toolbox.id, tool.id

    forbidden = await client.post(
        f"/api/v1/toolboxes/{toolbox_id}/tools/{tool_id}/request-maintenance",
        json={},
        headers=_auth(meca_token),
    )
    assert forbidden.status_code == 403


# --- Mantenimiento: documentos ocultos a Mecánico ---------------------------

async def test_maintenance_documents_hidden_from_mecanico(client):
    await _create_user("enc_doc6@test.com", "Clave123!", UserRole.encargado)
    await _create_user("meca_doc6@test.com", "Clave123!", UserRole.mecanico)
    encargado_token = await _login(client, "enc_doc6@test.com", "Clave123!")
    mecanico_token = await _login(client, "meca_doc6@test.com", "Clave123!")

    tool = (await client.post(
        "/api/v1/tools", json={"name": "Compresor Doc"}, headers=_auth(encargado_token)
    )).json()
    record = (await client.post(
        "/api/v1/maintenance",
        json={"tool_id": tool["id"], "reason": "Fuga de aire"},
        headers=_auth(encargado_token),
    )).json()

    await client.post(
        f"/api/v1/maintenance/{record['id']}/document",
        files={"file": ("foto.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 32, "image/png")},
        data={"title": "Foto de la falla"},
        headers=_auth(encargado_token),
    )

    as_encargado = await client.get(f"/api/v1/maintenance/{record['id']}", headers=_auth(encargado_token))
    assert len(as_encargado.json()["documents"]) == 1

    as_mecanico = await client.get(f"/api/v1/maintenance/{record['id']}", headers=_auth(mecanico_token))
    assert as_mecanico.status_code == 200
    assert as_mecanico.json()["documents"] == []

    listing_mecanico = await client.get("/api/v1/maintenance", headers=_auth(mecanico_token))
    row = next(r for r in listing_mecanico.json() if r["id"] == record["id"])
    assert row["documents"] == []


# --- Reportes: bloqueado para Mecánico --------------------------------------

async def test_reports_blocked_for_mecanico(client):
    await _create_user("meca_rep@test.com", "Clave123!", UserRole.mecanico)
    token = await _login(client, "meca_rep@test.com", "Clave123!")

    for path in ("/api/v1/reports/inventory", "/api/v1/reports/inventory.csv", "/api/v1/reports/loans"):
        res = await client.get(path, headers=_auth(token))
        assert res.status_code == 403, path
