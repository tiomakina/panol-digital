"""Pruebas del dashboard — KPIs, en particular el conteo de préstamos vencidos."""
from datetime import date, timedelta

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.loan import Loan, LoanStatus
from app.models.tool import Tool, ToolStatus
from app.models.user import User, UserRole


async def _create_user(email: str, password: str, role: UserRole) -> User:
    async with AsyncSessionLocal() as db:
        user = User(email=email, full_name="Test", role=role, hashed_password=hash_password(password))
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


async def _login(client, email, password) -> str:
    res = await client.post("/api/v1/auth/login", data={"username": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_overdue_kpi_counts_loans_regardless_of_celery_having_run(client):
    """
    Un préstamo vencido tiene que seguir contando como vencido tanto si Celery
    ya corrió y lo pasó a status=vencido, como si todavía dice "activo" pero
    ya venció (ventana antes de la corrida horaria). Antes del fix, el KPI
    solo miraba status=activo, así que un préstamo dejaba de "contar" como
    vencido justo cuando Celery lo procesaba — lo contrario de lo esperado.
    """
    jefe = await _create_user("jefe_kpi@test.com", "Clave123!", UserRole.jefe)
    mecanico = await _create_user("mecanico_kpi@test.com", "Clave123!", UserRole.mecanico)

    async with AsyncSessionLocal() as db:
        tool_a = Tool(name="Herramienta A", status=ToolStatus.prestado)
        tool_b = Tool(name="Herramienta B", status=ToolStatus.prestado)
        db.add_all([tool_a, tool_b])
        await db.flush()

        # Ya procesado por Celery (status=vencido)
        db.add(Loan(
            tool_id=tool_a.id, borrower_id=mecanico.id, issued_by_id=jefe.id,
            due_date=date.today() - timedelta(days=5), status=LoanStatus.vencido,
        ))
        # Todavía no procesado (sigue "activo" pero la fecha ya pasó)
        db.add(Loan(
            tool_id=tool_b.id, borrower_id=mecanico.id, issued_by_id=jefe.id,
            due_date=date.today() - timedelta(days=1), status=LoanStatus.activo,
        ))
        await db.commit()

    token = await _login(client, "mecanico_kpi@test.com", "Clave123!")
    kpis = await client.get("/api/v1/dashboard/kpis", headers=_auth(token))
    assert kpis.status_code == 200
    assert kpis.json()["overdue_loans"] == 2


async def test_tools_by_category_groups_and_excludes_baja(client):
    """
    El gráfico del dashboard antes mostraba números fijos (68/45/31/22) sin
    conexión a la base — este endpoint es el que lo reemplaza con datos
    reales, agrupados por categoría y sin contar las herramientas de baja
    (ya no son parte del inventario activo).
    """
    await _create_user("jefe_cat@test.com", "Clave123!", UserRole.jefe)
    token = await _login(client, "jefe_cat@test.com", "Clave123!")

    async with AsyncSessionLocal() as db:
        db.add_all([
            Tool(name="Taladro", category="Eléctricas", status=ToolStatus.disponible),
            Tool(name="Amoladora", category="Eléctricas", status=ToolStatus.prestado),
            Tool(name="Martillo", category="Manuales", status=ToolStatus.disponible),
            Tool(name="Sierra vieja", category="Eléctricas", status=ToolStatus.baja),  # no debe contar
            Tool(name="Sin categoría", category=None, status=ToolStatus.disponible),
        ])
        await db.commit()

    res = await client.get("/api/v1/dashboard/tools-by-category", headers=_auth(token))
    assert res.status_code == 200
    by_category = {row["category"]: row["count"] for row in res.json()}
    assert by_category["Eléctricas"] == 2  # no 3 — la de baja queda afuera
    assert by_category["Manuales"] == 1
    assert by_category["Sin categoría"] == 1
