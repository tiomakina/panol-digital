"""Pruebas del módulo de mantenimiento y de la baja de herramientas."""
from datetime import date

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.loan import Loan, LoanStatus
from app.models.tool import Tool, ToolStatus
from app.models.toolbox import Toolbox, ToolboxItem
from app.models.user import User, UserRole


async def _create_user(email: str, password: str, role: UserRole, full_name: str = "Test") -> int:
    async with AsyncSessionLocal() as db:
        user = User(email=email, full_name=full_name, role=role, hashed_password=hash_password(password))
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
