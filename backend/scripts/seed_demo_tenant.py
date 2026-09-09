"""
Script de seed para el tenant público de DEMO — Constructora Demo S.A.
Crea usuarios, tablas maestras y datos realistas para mostrar a prospectos.

Uso en el servidor:
  docker exec panol-digital-backend-1 python3 scripts/seed_demo_tenant.py

Es idempotente: si los usuarios ya existen, no falla ni duplica datos.

Credenciales del tenant demo:
  URL:        https://panol360.app/demo
  Jefe:       RUT 1-9       / Demo1234!
  Encargado:  RUT 2-7       / Demo1234!
  Mecánico:   RUT 3-5       / Demo1234!
"""
import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, create_tables
from app.core.security import hash_password
from app.models.loan import Loan, LoanStatus, ReturnCondition
from app.models.lookup import Brand, Category, Location, Provider
from app.models.maintenance import MaintenanceRecord, MaintenanceStatus
from app.models.tool import DepreciationMethod, Tool, ToolStatus
from app.models.user import User, UserRole

TENANT = "demo"

# ─── Usuarios demo ────────────────────────────────────────────────────────────
USERS = [
    {
        "rut": "1-9", "email": "jefe@demo.cl", "full_name": "Pedro Sánchez (Jefe de Bodega)",
        "role": UserRole.jefe, "password": "Demo1234!",
    },
    {
        "rut": "2-7", "email": "encargado@demo.cl", "full_name": "María González (Encargada)",
        "role": UserRole.encargado, "password": "Demo1234!",
    },
    {
        "rut": "3-5", "email": "mecanico@demo.cl", "full_name": "Carlos Muñoz (Mecánico)",
        "role": UserRole.mecanico, "password": "Demo1234!",
    },
]

# ─── Tablas maestras ──────────────────────────────────────────────────────────
BRANDS_DATA = ["Bosch", "Makita", "Stanley", "Gedore", "Fluke", "DeWalt", "Leica", "Hilti"]
CATEGORIES_DATA = ["Eléctricas", "Manuales", "Medición", "Neumáticas", "Seguridad"]
LOCATIONS_DATA = ["Bodega Principal", "Faena Norte", "Faena Sur", "Taller Central", "Vehículo 1"]
PROVIDERS_DATA = [
    {"name": "Ferretería Industrial López",  "rut": "76.123.456-7", "phone": "+56 2 2345 6789", "email": "ventas@lopez.cl"},
    {"name": "Distribuidora Herramientas SA", "rut": "77.987.654-3", "phone": "+56 2 8765 4321", "email": "contacto@dherr.cl"},
    {"name": "Servicio Técnico Bosch Chile",  "rut": "96.500.890-1", "phone": "+56 800 456 789", "email": "servicio@bosch.cl"},
]

# ─── Herramientas ─────────────────────────────────────────────────────────────
# (name, brand, category, location, status, price)
TOOLS_DATA = [
    # Disponibles
    ("Taladro percutor 18V", "Makita", "Eléctricas",  "Bodega Principal", "available",    189_990),
    ("Amoladora angular 7\"","Bosch",  "Eléctricas",  "Bodega Principal", "available",    124_990),
    ("Nivel láser de línea", "Leica",  "Medición",    "Bodega Principal", "available",    459_990),
    ("Multímetro digital",   "Fluke",  "Medición",    "Bodega Principal", "available",    89_990),
    ("Martillo demoledor",   "Hilti",  "Eléctricas",  "Taller Central",   "available",    389_990),
    ("Llave de torque 3/4\"","Stanley","Manuales",    "Bodega Principal", "available",    67_990),
    ("Compresor 50L",        "Schulz", "Neumáticas",  "Taller Central",   "available",    329_990),
    # Prestadas (status assigned below after loan creation)
    ("Sierra circular 7 1/4\"","DeWalt","Eléctricas", "Bodega Principal", "available",    215_990),
    ("Pistola de impacto 1/2\"","Gedore","Neumáticas","Bodega Principal", "available",    178_990),
    ("Cinta métrica 10m",    "Stanley","Manuales",    "Bodega Principal", "available",    12_990),
    # En mantenimiento (assigned below)
    ("Pulidora de banco",    "Bosch",  "Eléctricas",  "Taller Central",   "available",    145_990),
    # Dada de baja
    ("Taladro antiguo 12V",  "Makita", "Eléctricas",  "Bodega Principal", "retired",      0),
]


async def seed():
    await create_tables()
    async with AsyncSessionLocal() as db:
        print(f"\n{'═'*55}")
        print(f"  Seed tenant DEMO — Constructora Demo S.A.")
        print(f"{'═'*55}\n")

        # ── Usuarios ──────────────────────────────────────────────────────────
        print("── Usuarios ──────────────────────────────────────────")
        user_map: dict[str, User] = {}
        for data in USERS:
            existing = await db.execute(
                select(User).where(User.rut == data["rut"], User.tenant_id == TENANT)
            )
            u = existing.scalar_one_or_none()
            if u:
                print(f"  ⏭  {data['rut']} ya existe")
            else:
                u = User(
                    rut=data["rut"], email=data["email"], full_name=data["full_name"],
                    role=data["role"], hashed_password=hash_password(data["password"]),
                    tenant_id=TENANT, is_active=True,
                )
                db.add(u)
                await db.flush()
                print(f"  ✅ {data['full_name']} ({data['rut']})")
            user_map[data["role"].value] = u

        await db.flush()

        # ── Tablas maestras ───────────────────────────────────────────────────
        print("\n── Tablas maestras ───────────────────────────────────")
        brand_map: dict[str, Brand] = {}
        for name in BRANDS_DATA:
            r = await db.execute(select(Brand).where(Brand.name == name, Brand.tenant_id == TENANT))
            b = r.scalar_one_or_none()
            if not b:
                b = Brand(name=name, tenant_id=TENANT); db.add(b); await db.flush()
            brand_map[name] = b

        cat_map: dict[str, Category] = {}
        for name in CATEGORIES_DATA:
            r = await db.execute(select(Category).where(Category.name == name, Category.tenant_id == TENANT))
            c = r.scalar_one_or_none()
            if not c:
                c = Category(name=name, tenant_id=TENANT); db.add(c); await db.flush()
            cat_map[name] = c

        loc_map: dict[str, Location] = {}
        for name in LOCATIONS_DATA:
            r = await db.execute(select(Location).where(Location.name == name, Location.tenant_id == TENANT))
            l = r.scalar_one_or_none()
            if not l:
                l = Location(name=name, tenant_id=TENANT); db.add(l); await db.flush()
            loc_map[name] = l

        for pdata in PROVIDERS_DATA:
            r = await db.execute(select(Provider).where(Provider.name == pdata["name"], Provider.tenant_id == TENANT))
            if not r.scalar_one_or_none():
                db.add(Provider(
                    name=pdata["name"], rut=pdata["rut"],
                    phone=pdata["phone"], email=pdata["email"],
                    tenant_id=TENANT,
                ))
        await db.flush()
        print("  ✅ Marcas, categorías, ubicaciones, proveedores")

        # ── Herramientas ──────────────────────────────────────────────────────
        print("\n── Herramientas ──────────────────────────────────────")
        tool_map: dict[str, Tool] = {}
        for i, (tname, brand, cat, loc, status, price) in enumerate(TOOLS_DATA):
            r = await db.execute(
                select(Tool).where(Tool.name == tname, Tool.tenant_id == TENANT)
            )
            t = r.scalar_one_or_none()
            if t:
                print(f"  ⏭  {tname}")
            else:
                t = Tool(
                    name=tname,
                    code=f"DEMO-{i+1:03d}",
                    serial_number=f"SN-DEMO-{i+1:04d}",
                    status=ToolStatus(status),
                    purchase_price=price,
                    purchase_date=date.today() - timedelta(days=365 * 2),
                    depreciation_method=DepreciationMethod.lineal,
                    useful_life_years=5,
                    brand_id=brand_map[brand].id,
                    category_id=cat_map[cat].id,
                    location_id=loc_map[loc].id,
                    tenant_id=TENANT,
                )
                db.add(t)
                await db.flush()
                print(f"  ✅ {tname}")
            tool_map[tname] = t

        await db.flush()

        # ── Préstamos activos ─────────────────────────────────────────────────
        print("\n── Préstamos ─────────────────────────────────────────")
        mecanico = user_map.get("mecanico")
        jefe     = user_map.get("jefe")
        today    = date.today()

        # Herramientas a prestar
        to_loan = [
            ("Sierra circular 7 1/4\"",   mecanico, today - timedelta(days=3), today + timedelta(days=4), LoanStatus.activo),
            ("Pistola de impacto 1/2\"",  mecanico, today - timedelta(days=7), today - timedelta(days=1), LoanStatus.vencido),
            ("Cinta métrica 10m",         jefe,     today - timedelta(days=1), today + timedelta(days=6), LoanStatus.activo),
        ]

        for tname, borrower, loan_date, due_date, lstatus in to_loan:
            tool = tool_map.get(tname)
            if not tool:
                continue
            r = await db.execute(
                select(Loan).where(Loan.tool_id == tool.id, Loan.tenant_id == TENANT,
                                   Loan.status.in_([LoanStatus.activo, LoanStatus.vencido]))
            )
            if r.scalar_one_or_none():
                print(f"  ⏭  préstamo {tname}")
            else:
                loan = Loan(
                    tool_id=tool.id, borrower_id=borrower.id,
                    lender_id=jefe.id, tenant_id=TENANT,
                    loan_date=loan_date, due_date=due_date,
                    status=lstatus, notes="Préstamo de demo",
                )
                db.add(loan)
                tool.status = ToolStatus.prestada
                print(f"  ✅ {tname} → {borrower.full_name} ({lstatus.value})")

        await db.flush()

        # ── Mantenimiento ─────────────────────────────────────────────────────
        print("\n── Mantenimiento ─────────────────────────────────────")
        maint_tool = tool_map.get("Pulidora de banco")
        if maint_tool:
            r = await db.execute(
                select(MaintenanceRecord).where(
                    MaintenanceRecord.tool_id == maint_tool.id, MaintenanceRecord.tenant_id == TENANT
                )
            )
            if r.scalar_one_or_none():
                print("  ⏭  registro mantenimiento ya existe")
            else:
                rec = MaintenanceRecord(
                    tool_id=maint_tool.id, tenant_id=TENANT,
                    reason="Desgaste en disco + chispazo en motor",
                    provider="Servicio Técnico Bosch Chile",
                    sent_date=today - timedelta(days=10),
                    status=MaintenanceStatus.en_proceso,
                )
                db.add(rec)
                maint_tool.status = ToolStatus.en_mantenimiento
                print("  ✅ Pulidora de banco → en mantenimiento (Bosch)")

        await db.flush()
        await db.commit()

        print(f"\n{'═'*55}")
        print("  ✅ Tenant DEMO listo")
        print(f"{'═'*55}")
        print("\n  Acceso:")
        print("  URL:        https://panol360.app/demo")
        print("  Jefe:       RUT 1-9    / Demo1234!")
        print("  Encargado:  RUT 2-7    / Demo1234!")
        print("  Mecánico:   RUT 3-5    / Demo1234!")
        print()


if __name__ == "__main__":
    asyncio.run(seed())
