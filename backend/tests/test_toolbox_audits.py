"""Pruebas del módulo de auditoría/inventario de cajas de herramientas."""
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.tool import Tool, ToolStatus
from app.models.toolbox import Toolbox, ToolboxItem
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


async def _seed_toolbox_with_two_tools() -> tuple[int, int, int]:
    async with AsyncSessionLocal() as db:
        toolbox = Toolbox(name="Caja Auditoría QA")
        tool_a = Tool(name="Llave Francesa", status=ToolStatus.en_caja)
        tool_b = Tool(name="Destornillador Phillips", status=ToolStatus.en_caja)
        db.add_all([toolbox, tool_a, tool_b])
        await db.flush()
        db.add_all([
            ToolboxItem(toolbox_id=toolbox.id, tool_id=tool_a.id),
            ToolboxItem(toolbox_id=toolbox.id, tool_id=tool_b.id),
        ])
        await db.commit()
        return toolbox.id, tool_a.id, tool_b.id


async def test_audit_lifecycle_bueno_and_faltante(client):
    # Auditar es Encargado+ desde el pedido del cliente de restringir Cajas —
    # un Mecánico ya no puede crear/editar auditorías (ver
    # test_mecanico_cannot_audit_but_can_view_completed_ones más abajo).
    await _create_user("enc_aud@test.com", "Clave123!", UserRole.encargado)
    token = await _login(client, "enc_aud@test.com", "Clave123!")
    toolbox_id, tool_a_id, tool_b_id = await _seed_toolbox_with_two_tools()

    created = await client.post("/api/v1/toolbox-audits", json={"toolbox_id": toolbox_id}, headers=_auth(token))
    assert created.status_code == 201, created.text
    audit = created.json()
    assert audit["status"] == "en_progreso"
    assert len(audit["items"]) == 2
    item_a = next(i for i in audit["items"] if i["tool_id"] == tool_a_id)
    item_b = next(i for i in audit["items"] if i["tool_id"] == tool_b_id)

    # No se puede abrir una segunda auditoría mientras esta sigue abierta
    dup = await client.post("/api/v1/toolbox-audits", json={"toolbox_id": toolbox_id}, headers=_auth(token))
    assert dup.status_code == 400

    # No se puede cerrar con items sin revisar
    early_close = await client.post(f"/api/v1/toolbox-audits/{audit['id']}/complete", headers=_auth(token))
    assert early_close.status_code == 400

    # Marcar "faltante" sin observación debe fallar
    missing_no_obs = await client.put(
        f"/api/v1/toolbox-audits/{audit['id']}/items/{item_a['id']}",
        json={"condition": "faltante"},
        headers=_auth(token),
    )
    assert missing_no_obs.status_code == 400

    # Con observación sí funciona
    missing_ok = await client.put(
        f"/api/v1/toolbox-audits/{audit['id']}/items/{item_a['id']}",
        json={"condition": "faltante", "observation": "No estaba en la caja, se va a preguntar al turno anterior"},
        headers=_auth(token),
    )
    assert missing_ok.status_code == 200, missing_ok.text
    assert missing_ok.json()["condition"] == "faltante"

    good = await client.put(
        f"/api/v1/toolbox-audits/{audit['id']}/items/{item_b['id']}",
        json={"condition": "bueno"},
        headers=_auth(token),
    )
    assert good.status_code == 200

    completed = await client.post(f"/api/v1/toolbox-audits/{audit['id']}/complete", headers=_auth(token))
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completado"
    assert completed.json()["completed_at"] is not None

    # Ya cerrada, no admite más cambios
    reopen_attempt = await client.put(
        f"/api/v1/toolbox-audits/{audit['id']}/items/{item_b['id']}",
        json={"condition": "dañado", "observation": "test"},
        headers=_auth(token),
    )
    assert reopen_attempt.status_code == 400


async def test_send_audit_item_to_maintenance_removes_from_toolbox(client):
    await _create_user("enc_aud2@test.com", "Clave123!", UserRole.encargado)
    token = await _login(client, "enc_aud2@test.com", "Clave123!")
    toolbox_id, tool_a_id, tool_b_id = await _seed_toolbox_with_two_tools()

    created = await client.post("/api/v1/toolbox-audits", json={"toolbox_id": toolbox_id}, headers=_auth(token))
    audit = created.json()
    item_a = next(i for i in audit["items"] if i["tool_id"] == tool_a_id)
    item_b = next(i for i in audit["items"] if i["tool_id"] == tool_b_id)

    sent = await client.post(
        f"/api/v1/toolbox-audits/{audit['id']}/items/{item_a['id']}/send-to-maintenance",
        json={"provider": "Taller Central", "reason": "Mordaza trabada"},
        headers=_auth(token),
    )
    assert sent.status_code == 200, sent.text
    body = sent.json()
    assert body["sent_to_maintenance"] is True
    assert body["condition"] == "dañado"

    # La herramienta salió de la caja y quedó en mantenimiento
    tool_check = await client.get(f"/api/v1/tools/{tool_a_id}", headers=_auth(token))
    assert tool_check.json()["status"] == "mantenimiento"
    box_check = await client.get(f"/api/v1/toolboxes/{toolbox_id}", headers=_auth(token))
    assert all(i["tool_id"] != tool_a_id for i in box_check.json()["items"])

    # Y quedó un registro en el módulo de mantenimiento
    maint = await client.get(f"/api/v1/maintenance?tool_id={tool_a_id}", headers=_auth(token))
    assert len(maint.json()) == 1
    assert maint.json()[0]["provider"] == "Taller Central"

    # No se puede enviar dos veces
    again = await client.post(
        f"/api/v1/toolbox-audits/{audit['id']}/items/{item_a['id']}/send-to-maintenance",
        json={"reason": "otra vez"},
        headers=_auth(token),
    )
    assert again.status_code == 400

    # Cerrar la auditoría todavía exige revisar la otra herramienta
    close_attempt = await client.post(f"/api/v1/toolbox-audits/{audit['id']}/complete", headers=_auth(token))
    assert close_attempt.status_code == 400

    await client.put(
        f"/api/v1/toolbox-audits/{audit['id']}/items/{item_b['id']}",
        json={"condition": "bueno"},
        headers=_auth(token),
    )
    closed = await client.post(f"/api/v1/toolbox-audits/{audit['id']}/complete", headers=_auth(token))
    assert closed.status_code == 200


async def test_mecanico_cannot_audit_but_can_view_completed_ones(client):
    """
    Pedido del cliente: un Mecánico ya no puede auditar cajas (eso quedó en
    Encargado+), pero sí tiene que poder ver el historial de auditorías ya
    hechas — la lista/detalle sigue abierta a cualquier rol autenticado.
    """
    await _create_user("enc_aud3@test.com", "Clave123!", UserRole.encargado)
    await _create_user("meca_aud3@test.com", "Clave123!", UserRole.mecanico)
    encargado_token = await _login(client, "enc_aud3@test.com", "Clave123!")
    mecanico_token = await _login(client, "meca_aud3@test.com", "Clave123!")
    toolbox_id, tool_a_id, tool_b_id = await _seed_toolbox_with_two_tools()

    forbidden_create = await client.post(
        "/api/v1/toolbox-audits", json={"toolbox_id": toolbox_id}, headers=_auth(mecanico_token)
    )
    assert forbidden_create.status_code == 403

    created = await client.post(
        "/api/v1/toolbox-audits", json={"toolbox_id": toolbox_id}, headers=_auth(encargado_token)
    )
    audit = created.json()
    item_a = next(i for i in audit["items"] if i["tool_id"] == tool_a_id)

    forbidden_update = await client.put(
        f"/api/v1/toolbox-audits/{audit['id']}/items/{item_a['id']}",
        json={"condition": "bueno"},
        headers=_auth(mecanico_token),
    )
    assert forbidden_update.status_code == 403

    forbidden_complete = await client.post(
        f"/api/v1/toolbox-audits/{audit['id']}/complete", headers=_auth(mecanico_token)
    )
    assert forbidden_complete.status_code == 403

    # Pero sí puede ver la lista y el detalle
    listing = await client.get(
        f"/api/v1/toolbox-audits?toolbox_id={toolbox_id}", headers=_auth(mecanico_token)
    )
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    detail = await client.get(f"/api/v1/toolbox-audits/{audit['id']}", headers=_auth(mecanico_token))
    assert detail.status_code == 200
