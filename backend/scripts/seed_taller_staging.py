"""
Seed de STAGING — Taller Mecánico Demo
Crea un escenario realista de taller automotriz con 6 personas, 7 cajas de
herramientas, herramientas en todos los estados posibles y préstamos activos.

Uso en el servidor:
  docker exec panol-digital-backend-staging-1 python3 scripts/seed_taller_staging.py

Es idempotente: si los usuarios ya existen, no falla ni duplica datos.

Credenciales del staging (tenant vms-ingenieria):
  URL:            https://staging.panol360.app
  Jefe:           RUT 10-8  / Taller2024!
  Supervisor 1:   RUT 11-6  / Taller2024!
  Supervisor 2:   RUT 12-4  / Taller2024!
  Mecánico 1:     RUT 13-2  / Taller2024! (banda roja)
  Mecánico 2:     RUT 14-0  / Taller2024! (banda azul)
  Mecánico 3:     RUT 15-9  / Taller2024! (banda amarilla)

Nota sobre préstamos a terceros externos:
  El sistema solo permite prestar a usuarios internos. Para un mecánico o
  taller externo, el workaround hoy es crear un usuario con rol mecánico
  cuyo nombre identifique al tercero. Ver usuario RUT 16-7 en este seed.
  El campo description/notes del préstamo documenta que es externo.
"""
import asyncio
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, create_tables
from app.core.security import hash_password
from app.models.loan import Loan, LoanStatus
from app.models.lookup import Brand, Category, Location, Provider
from app.models.maintenance import MaintenanceRecord, MaintenanceStatus
from app.models.tool import DepreciationMethod, Tool, ToolStatus
from app.models.toolbox import Toolbox, ToolboxItem
from app.models.user import User, UserRole
from app.services.qr_service import generate_tool_qr, generate_toolbox_qr

TENANT = "vms-ingenieria"
PASSWORD = "Taller2024!"

# ── Usuarios ──────────────────────────────────────────────────────────────────
USERS = [
    {
        "rut": "10-8", "email": "jefe@taller.cl",
        "full_name": "Carlos Mendoza (Jefe de Taller)",
        "role": UserRole.jefe,
    },
    {
        "rut": "11-6", "email": "supervisor1@taller.cl",
        "full_name": "Pedro Soto (Supervisor)",
        "role": UserRole.encargado,
    },
    {
        "rut": "12-4", "email": "supervisor2@taller.cl",
        "full_name": "Luis Vega (Supervisor)",
        "role": UserRole.encargado,
    },
    {
        "rut": "13-2", "email": "roberto@taller.cl",
        "full_name": "Roberto Díaz (Mecánico 🔴)",
        "role": UserRole.mecanico,
    },
    {
        "rut": "14-0", "email": "juan@taller.cl",
        "full_name": "Juan Pérez (Mecánico 🔵)",
        "role": UserRole.mecanico,
    },
    {
        "rut": "15-9", "email": "miguel@taller.cl",
        "full_name": "Miguel Torres (Mecánico 🟡)",
        "role": UserRole.mecanico,
    },
    # Usuario especial para préstamos a terceros externos.
    # El nombre indica que es un tercero, no un empleado real.
    # Workaround hasta que se agregue campo "prestatario externo" al modelo.
    {
        "rut": "16-7", "email": "externo@taller.cl",
        "full_name": "⚠ Externo — Taller El Rápido (Proveedor)",
        "role": UserRole.mecanico,
    },
]

# ── Tablas maestras ───────────────────────────────────────────────────────────
BRANDS_DATA = ["Bosch", "Stanley", "Gedore", "KTC", "Urrea", "Snap-on", "Inflex", "Schulz", "Mac Tools"]
CATEGORIES_DATA = ["Manuales", "Eléctricas", "Neumáticas", "Medición", "Diagnóstico", "Elevación", "Seguridad"]
LOCATIONS_DATA = [
    "Caja Taller General",
    "Caja Carlos Mendoza",
    "Caja Pedro Soto",
    "Caja Luis Vega",
    "Caja Roberto Díaz",
    "Caja Juan Pérez",
    "Caja Miguel Torres",
    "Bodega",
    "Área de Lavado",
    "Foso de Inspección",
]
PROVIDERS_DATA = [
    {"name": "Ferretería Industrial Del Solar", "rut": "76.111.222-3", "phone": "+56 2 2345 1111", "email": "ventas@delsolar.cl"},
    {"name": "Distribuidora Automotriz SA",     "rut": "77.333.444-5", "phone": "+56 2 8888 9999", "email": "contacto@dautomotriz.cl"},
    {"name": "Servicio Técnico Bosch Chile",    "rut": "96.500.890-1", "phone": "+56 800 123 456", "email": "servicio@bosch.cl"},
]

# ── Herramientas ──────────────────────────────────────────────────────────────
# Formato: (name, brand, category, location, status, cost_clp, product_code, serial, description)
# product_code IGUAL en 3 unidades del mismo producto → sistema las agrupa
# serial_number ÚNICO por unidad física → es el identificador real
# description con color de banda → diferenciación visual cuando están fuera de caja

TODAY = date.today()

TOOLS = [
    # ── 3 alicates cortantes idénticos — uno por mecánico, diferenciados por color ──
    ("Alicate Cortante 7\"",   "Stanley", "Manuales", "Caja Roberto Díaz",  "en_caja",    15_990, "STN-AC7",  "SN-AC-001", "Banda roja en mango — asignado a Roberto Díaz"),
    ("Alicate Cortante 7\"",   "Stanley", "Manuales", "Caja Juan Pérez",    "en_caja",    15_990, "STN-AC7",  "SN-AC-002", "Banda azul en mango — asignado a Juan Pérez"),
    ("Alicate Cortante 7\"",   "Stanley", "Manuales", "Caja Miguel Torres", "en_caja",    15_990, "STN-AC7",  "SN-AC-003", "Banda amarilla en mango — asignado a Miguel Torres"),

    # ── 3 llaves combinadas idénticas — una por mecánico ──────────────────────
    ("Llave Combinada 17mm",   "Gedore",  "Manuales", "Caja Roberto Díaz",  "en_caja",    12_500, "GED-LC17", "SN-LC-001", "Banda roja en mango — asignado a Roberto Díaz"),
    ("Llave Combinada 17mm",   "Gedore",  "Manuales", "Caja Juan Pérez",    "en_caja",    12_500, "GED-LC17", "SN-LC-002", "Banda azul en mango — asignado a Juan Pérez"),
    ("Llave Combinada 17mm",   "Gedore",  "Manuales", "Caja Miguel Torres", "en_caja",    12_500, "GED-LC17", "SN-LC-003", "Banda amarilla en mango — asignado a Miguel Torres"),

    # ── Juegos por mecánico ───────────────────────────────────────────────────
    ("Juego de Dados 1/2\" (20pz)", "KTC",    "Manuales", "Caja Roberto Díaz",  "en_caja", 89_990, "KTC-JD20", "SN-JD-001", "Banda roja en estuche — Roberto Díaz"),
    ("Juego de Dados 1/2\" (20pz)", "KTC",    "Manuales", "Caja Juan Pérez",    "en_caja", 89_990, "KTC-JD20", "SN-JD-002", "Banda azul en estuche — Juan Pérez"),
    ("Juego de Dados 1/2\" (20pz)", "KTC",    "Manuales", "Caja Miguel Torres", "en_caja", 89_990, "KTC-JD20", "SN-JD-003", "Banda amarilla en estuche — Miguel Torres"),

    # ── Herramientas compartidas del taller (caja general) ────────────────────
    ("Llave de Torque 3/4\" 300Nm",  "Snap-on",  "Manuales",    "Caja Taller General", "en_caja",   245_000, "SNAP-TQ300", "SN-TQ-001", "Uso compartido — verificar calibración semestral"),
    ("Pistola Neumática 1/2\"",      "Inflex",   "Neumáticas",  "Caja Taller General", "en_caja",   129_990, "INF-PN12",  "SN-PN-001", "Uso compartido"),
    ("Pistola Neumática 1/2\"",      "Inflex",   "Neumáticas",  "Caja Taller General", "en_caja",   129_990, "INF-PN12",  "SN-PN-002", "Uso compartido — 2da unidad"),
    ("Compresor de Aire 50L",        "Schulz",   "Neumáticas",  "Foso de Inspección",  "disponible",329_990, "SCH-CA50",  "SN-CA-001", "Equipo fijo del taller"),
    ("Gata Hidráulica 2 Ton",        "Urrea",    "Elevación",   "Foso de Inspección",  "disponible", 89_990, "URR-GH2T",  "SN-GH-001", "Uso compartido — almacenar siempre en foso"),
    ("Gata Hidráulica 2 Ton",        "Urrea",    "Elevación",   "Foso de Inspección",  "disponible", 89_990, "URR-GH2T",  "SN-GH-002", "Uso compartido — 2da unidad"),

    # ── Herramientas de diagnóstico (cajas supervisores) ──────────────────────
    ("Scanner OBD2 Profesional",     "Bosch",    "Diagnóstico", "Caja Pedro Soto",    "en_caja",   389_990, "BSH-OBD2",  "SN-OBD-001", "Acceso solo supervisores — no prestar a mecánicos sin autorización"),
    ("Multímetro Digital TRMS",      "Bosch",    "Diagnóstico", "Caja Luis Vega",     "en_caja",    89_990, "BSH-MM1",   "SN-MM-001",  "Acceso solo supervisores"),
    ("Osciloscopio Automotriz 2ch",  "Mac Tools","Diagnóstico", "Caja Luis Vega",     "en_caja",   890_000, "MAC-OSC2",  "SN-OSC-001", "Equipo delicado — transportar en estuche rígido"),

    # ── Herramientas del jefe ─────────────────────────────────────────────────
    ("Extractor de Poleas Universal","KTC",      "Manuales",    "Caja Carlos Mendoza","en_caja",    67_990, "KTC-EP1",   "SN-EP-001",  "Uso exclusivo jefatura"),
    ("Micrómetro 0-25mm",           "Gedore",   "Medición",    "Caja Carlos Mendoza","en_caja",   145_000, "GED-MIC25", "SN-MIC-001", "Calibrado — próxima calibración: 01/06/2027"),

    # ── Herramientas disponibles (en bodega, listas para prestar) ─────────────
    ("Lámpara de Foso LED",         "Bosch",    "Eléctricas",  "Bodega",             "disponible",  34_990, "BSH-LED1",  "SN-LED-001", None),
    ("Extensión Eléctrica 10m",     "Stanley",  "Eléctricas",  "Bodega",             "disponible",  18_990, "STN-EXT10", "SN-EXT-001", None),

    # ── Herramienta prestada actualmente (préstamo activo) ────────────────────
    ("Llave de Impacto Eléctrica",  "Bosch",    "Eléctricas",  "Caja Roberto Díaz",  "prestado",   199_990, "BSH-IMP1",  "SN-IMP-001", "Prestada temporalmente para trabajo externo"),

    # ── Herramienta en mantenimiento ──────────────────────────────────────────
    ("Pistola de Calor 2000W",      "Bosch",    "Eléctricas",  "Bodega",             "disponible", 54_990, "BSH-HC1",   "SN-HC-001",  "Falla en selector de temperatura — enviada a servicio técnico"),

    # ── Herramienta dada de baja definitiva ───────────────────────────────────
    ("Taladro Percutor 12V (antiguo)","Bosch",  "Eléctricas",  "Bodega",             "baja",        0,     "BSH-TAL12", "SN-TAL-OLD", "Dada de baja por obsolescencia — batería sin repuesto en mercado"),
    ("Llave Combinada 14mm (rota)",  "Urrea",   "Manuales",    "Bodega",             "baja",        0,     "URR-LC14",  "SN-LC-ROTA", "Dada de baja por rotura — fractura en cuello"),
]


async def seed():
    await create_tables()
    async with AsyncSessionLocal() as db:
        print(f"\n{'═'*60}")
        print(f"  Seed Staging — Taller Mecánico Demo ({TENANT})")
        print(f"{'═'*60}\n")

        # ── Usuarios ──────────────────────────────────────────────────────────
        print("── Usuarios ──────────────────────────────────────────────")
        user_map: dict[str, User] = {}
        for data in USERS:
            r = await db.execute(select(User).where(User.rut == data["rut"], User.tenant_id == TENANT))
            u = r.scalar_one_or_none()
            if u:
                print(f"  ⏭  {data['rut']} ya existe ({data['full_name']})")
            else:
                u = User(
                    rut=data["rut"], email=data["email"],
                    full_name=data["full_name"], role=data["role"],
                    hashed_password=hash_password(PASSWORD),
                    tenant_id=TENANT, is_active=True,
                )
                db.add(u)
                await db.flush()
                print(f"  ✅ {data['full_name']} (RUT {data['rut']})")
            user_map[data["rut"]] = u
        await db.flush()

        # Atajos por rol
        jefe       = user_map["10-8"]
        supervisor1 = user_map["11-6"]
        supervisor2 = user_map["12-4"]
        mecanico1  = user_map["13-2"]
        mecanico2  = user_map["14-0"]
        mecanico3  = user_map["15-9"]
        externo    = user_map["16-7"]

        # ── Tablas maestras ───────────────────────────────────────────────────
        print("\n── Tablas maestras ───────────────────────────────────────")
        for name in BRANDS_DATA:
            r = await db.execute(select(Brand).where(Brand.name == name, Brand.tenant_id == TENANT))
            if not r.scalar_one_or_none():
                db.add(Brand(name=name, tenant_id=TENANT))
        for name in CATEGORIES_DATA:
            r = await db.execute(select(Category).where(Category.name == name, Category.tenant_id == TENANT))
            if not r.scalar_one_or_none():
                db.add(Category(name=name, tenant_id=TENANT))
        for name in LOCATIONS_DATA:
            r = await db.execute(select(Location).where(Location.name == name, Location.tenant_id == TENANT))
            if not r.scalar_one_or_none():
                db.add(Location(name=name, tenant_id=TENANT))
        for p in PROVIDERS_DATA:
            r = await db.execute(select(Provider).where(Provider.name == p["name"], Provider.tenant_id == TENANT))
            if not r.scalar_one_or_none():
                db.add(Provider(name=p["name"], rut=p["rut"], phone=p["phone"], email=p["email"], tenant_id=TENANT))
        await db.flush()
        print("  ✅ Marcas, categorías, ubicaciones, proveedores")

        # ── Herramientas ──────────────────────────────────────────────────────
        print("\n── Herramientas ──────────────────────────────────────────")
        tool_map: dict[str, Tool] = {}
        for i, (tname, brand, cat, loc, status, cost, pcode, serial, desc) in enumerate(TOOLS):
            r = await db.execute(select(Tool).where(Tool.serial_number == serial, Tool.tenant_id == TENANT))
            t = r.scalar_one_or_none()
            if t:
                print(f"  ⏭  {serial} ya existe")
            else:
                t = Tool(
                    name=tname, brand=brand, category=cat, location=loc,
                    status=ToolStatus(status),
                    purchase_cost=Decimal(cost),
                    purchase_date=TODAY - timedelta(days=365 * 2 + i * 10),
                    salvage_value=Decimal(cost) * Decimal("0.10"),
                    useful_life_years=5,
                    depreciation_method=DepreciationMethod.lineal,
                    product_code=pcode,
                    serial_number=serial,
                    description=desc,
                    tenant_id=TENANT,
                )
                db.add(t)
                await db.flush()
                t.qr_code_url = generate_tool_qr(t.id)
                print(f"  ✅ {tname} [{serial}]")
            tool_map[serial] = t
        await db.flush()

        # Marcar baja definitiva (ya tienen status=baja, agregar motivo)
        t_baja1 = tool_map["SN-TAL-OLD"]
        if not t_baja1.decommission_reason:
            t_baja1.decommission_reason = "Obsolescencia tecnológica — batería NiCd sin repuesto disponible en el mercado"
            t_baja1.decommission_date = TODAY - timedelta(days=180)
            t_baja1.decommission_authorized_by_id = jefe.id

        t_baja2 = tool_map["SN-LC-ROTA"]
        if not t_baja2.decommission_reason:
            t_baja2.decommission_reason = "Fractura estructural en cuello — riesgo de accidente laboral si se usa"
            t_baja2.decommission_date = TODAY - timedelta(days=45)
            t_baja2.decommission_authorized_by_id = supervisor1.id

        await db.flush()

        # ── Mantenimiento (pistola de calor) ──────────────────────────────────
        print("\n── Mantenimiento ─────────────────────────────────────────")
        t_mant = tool_map["SN-HC-001"]
        r = await db.execute(
            select(MaintenanceRecord).where(
                MaintenanceRecord.tool_id == t_mant.id,
                MaintenanceRecord.tenant_id == TENANT,
            )
        )
        if not r.scalar_one_or_none():
            t_mant.status = ToolStatus.mantenimiento
            maint = MaintenanceRecord(
                tool_id=t_mant.id,
                tenant_id=TENANT,
                created_by_id=supervisor1.id,
                status=MaintenanceStatus.en_proceso,
                reason="Falla en selector de temperatura — no conmuta entre posiciones 1 y 2",
                sent_date=TODAY - timedelta(days=7),
                provider="Servicio Técnico Bosch Chile",
            )
            db.add(maint)
            await db.flush()
            print("  ✅ Pistola de calor en mantenimiento (Bosch)")
        else:
            print("  ⏭  Mantenimiento ya existe")

        # ── Cajas de herramientas ─────────────────────────────────────────────
        print("\n── Cajas de herramientas ─────────────────────────────────")
        TOOLBOXES = [
            ("Caja Taller General",   "Herramientas compartidas del taller — uso libre con autorización", "Área de Lavado", None),
            ("Caja Carlos Mendoza",   "Jefe de Taller",         "Oficina Jefatura", jefe.id),
            ("Caja Pedro Soto",       "Supervisor Pedro Soto",  "Sala Supervisores", supervisor1.id),
            ("Caja Luis Vega",        "Supervisor Luis Vega",   "Sala Supervisores", supervisor2.id),
            ("Caja Roberto Díaz 🔴",  "Mecánico Roberto Díaz — banda roja", "Puesto 1", mecanico1.id),
            ("Caja Juan Pérez 🔵",    "Mecánico Juan Pérez — banda azul",   "Puesto 2", mecanico2.id),
            ("Caja Miguel Torres 🟡", "Mecánico Miguel Torres — banda amarilla", "Puesto 3", mecanico3.id),
        ]
        toolbox_map: dict[str, Toolbox] = {}
        for tb_name, tb_desc, tb_loc, tb_resp in TOOLBOXES:
            r = await db.execute(select(Toolbox).where(Toolbox.name == tb_name, Toolbox.tenant_id == TENANT))
            tb = r.scalar_one_or_none()
            if tb:
                print(f"  ⏭  {tb_name} ya existe")
            else:
                tb = Toolbox(
                    name=tb_name, description=tb_desc, location=tb_loc,
                    responsible_user_id=tb_resp, tenant_id=TENANT,
                )
                db.add(tb)
                await db.flush()
                tb.qr_code_url = generate_toolbox_qr(tb.id)
                print(f"  ✅ {tb_name}")
            toolbox_map[tb_name] = tb
        await db.flush()

        # ── Asignar herramientas a cajas ──────────────────────────────────────
        print("\n── Asignando herramientas a cajas ────────────────────────")
        CAJA_TOOLS: list[tuple[str, list[str]]] = [
            ("Caja Taller General", ["SN-TQ-001", "SN-PN-001", "SN-PN-002"]),
            ("Caja Carlos Mendoza", ["SN-EP-001", "SN-MIC-001"]),
            ("Caja Pedro Soto",     ["SN-OBD-001"]),
            ("Caja Luis Vega",      ["SN-MM-001", "SN-OSC-001"]),
            ("Caja Roberto Díaz 🔴", ["SN-AC-001", "SN-LC-001", "SN-JD-001"]),
            ("Caja Juan Pérez 🔵",   ["SN-AC-002", "SN-LC-002", "SN-JD-002"]),
            ("Caja Miguel Torres 🟡",["SN-AC-003", "SN-LC-003", "SN-JD-003"]),
        ]
        for tb_name, serials in CAJA_TOOLS:
            tb = toolbox_map[tb_name]
            for serial in serials:
                tool = tool_map.get(serial)
                if not tool:
                    continue
                r = await db.execute(select(ToolboxItem).where(ToolboxItem.tool_id == tool.id))
                if not r.scalar_one_or_none():
                    db.add(ToolboxItem(toolbox_id=tb.id, tool_id=tool.id))
                    print(f"  ✅ {serial} → {tb_name}")
        await db.flush()

        # ── Préstamos ─────────────────────────────────────────────────────────
        print("\n── Préstamos ─────────────────────────────────────────────")

        # 1. Préstamo activo normal — llave de impacto a Roberto
        t_prestado = tool_map["SN-IMP-001"]
        r = await db.execute(select(Loan).where(Loan.tool_id == t_prestado.id, Loan.tenant_id == TENANT))
        if not r.scalar_one_or_none():
            loan1 = Loan(
                tool_id=t_prestado.id,
                borrower_id=mecanico1.id,
                issued_by_id=supervisor1.id,
                loan_date=TODAY - timedelta(days=3),
                due_date=TODAY + timedelta(days=4),
                status=LoanStatus.activo,
                purpose="Trabajo en vehículo 2015 — cambio de embrague",
                notes="Revisar estado al devolver — operó con fricción inusual",
                tenant_id=TENANT,
            )
            db.add(loan1)
            t_prestado.status = ToolStatus.prestado
            print(f"  ✅ Préstamo activo: Llave de Impacto → Roberto Díaz (vence {TODAY + timedelta(days=4)})")

        # 2. Préstamo VENCIDO — scanner OBD2 (simula alerta de campana)
        t_obd = tool_map["SN-OBD-001"]
        r = await db.execute(select(Loan).where(Loan.tool_id == t_obd.id, Loan.tenant_id == TENANT, Loan.status == LoanStatus.vencido))
        if not r.scalar_one_or_none():
            loan2 = Loan(
                tool_id=t_obd.id,
                borrower_id=mecanico2.id,
                issued_by_id=supervisor2.id,
                loan_date=TODAY - timedelta(days=10),
                due_date=TODAY - timedelta(days=3),  # Venció hace 3 días
                status=LoanStatus.vencido,
                purpose="Diagnóstico en domicilio del cliente — VW Passat 2018",
                notes="Préstamo vencido — no ha sido devuelto. Contactar a Juan Pérez.",
                tenant_id=TENANT,
            )
            db.add(loan2)
            t_obd.status = ToolStatus.prestado
            print(f"  ✅ Préstamo VENCIDO: Scanner OBD2 → Juan Pérez (venció hace 3 días) ⚠")

        # 3. Préstamo a TALLER EXTERNO (usuario "externo") — osciloscopio
        t_osc = tool_map["SN-OSC-001"]
        r = await db.execute(select(Loan).where(Loan.tool_id == t_osc.id, Loan.tenant_id == TENANT, Loan.status == LoanStatus.activo))
        if not r.scalar_one_or_none():
            loan3 = Loan(
                tool_id=t_osc.id,
                borrower_id=externo.id,
                issued_by_id=jefe.id,
                loan_date=TODAY - timedelta(days=1),
                due_date=TODAY + timedelta(days=2),
                status=LoanStatus.activo,
                purpose="Préstamo a Taller El Rápido — diagnóstico urgente cliente compartido",
                notes="PRÉSTAMO EXTERNO — Responsable: Rodrigo Pizarro, cel +569 9876 5432. "
                      "Requiere garantía firmada (ver carpeta física en recepción).",
                tenant_id=TENANT,
            )
            db.add(loan3)
            t_osc.status = ToolStatus.prestado
            print(f"  ✅ Préstamo EXTERNO: Osciloscopio → Taller El Rápido (usuario 'externo')")

        # 4. Préstamo devuelto — historial
        t_led = tool_map["SN-LED-001"]
        r = await db.execute(select(Loan).where(Loan.tool_id == t_led.id, Loan.tenant_id == TENANT))
        if not r.scalar_one_or_none():
            from app.models.loan import ReturnCondition
            loan4 = Loan(
                tool_id=t_led.id,
                borrower_id=mecanico3.id,
                issued_by_id=supervisor1.id,
                loan_date=TODAY - timedelta(days=14),
                due_date=TODAY - timedelta(days=7),
                return_date=datetime.combine(TODAY - timedelta(days=8), datetime.min.time()),
                status=LoanStatus.devuelto,
                return_condition=ReturnCondition.bueno,
                purpose="Trabajo nocturno — revisión de frenos",
                tenant_id=TENANT,
            )
            db.add(loan4)
            print(f"  ✅ Préstamo devuelto (historial): Lámpara LED → Miguel Torres")

        await db.commit()

        print(f"\n{'═'*60}")
        print("  ✅ Seed completado exitosamente")
        print(f"{'═'*60}")
        print(f"""
Acceso al staging:
  URL:          https://staging.panol360.app
  Jefe:         RUT 10-8  / {PASSWORD}
  Supervisor 1: RUT 11-6  / {PASSWORD}
  Supervisor 2: RUT 12-4  / {PASSWORD}
  Mecánico 1:   RUT 13-2  / {PASSWORD}  (Roberto Díaz 🔴)
  Mecánico 2:   RUT 14-0  / {PASSWORD}  (Juan Pérez 🔵)
  Mecánico 3:   RUT 15-9  / {PASSWORD}  (Miguel Torres 🟡)
  Externo:      RUT 16-7  / {PASSWORD}  (Taller El Rápido)
""")


if __name__ == "__main__":
    asyncio.run(seed())
