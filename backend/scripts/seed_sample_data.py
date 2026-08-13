"""
Script de datos de EJEMPLO — carga un caso de uso completo y coherente
para probar el sistema con algo más que una base vacía: tablas maestras,
herramientas en todos los estados posibles, préstamos, una caja de
herramientas con auditoría, y el historial de mantenimiento/baja que
explica CÓMO llegó cada herramienta a su estado actual (no solo el
estado final suelto, sino los registros que lo justifican).

Requiere que ya corriste `python scripts/seed_data.py` (los 3 usuarios base).
Es idempotente: si ya hay herramientas cargadas, no hace nada (para no
duplicar datos en cada corrida).

Uso: docker-compose exec backend python scripts/seed_sample_data.py
     (o `python scripts/seed_sample_data.py` desde backend/ en desarrollo local)
"""
import asyncio
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, create_tables
from app.models.loan import Loan, LoanStatus, ReturnCondition
from app.models.lookup import Brand, Category, Location, Provider
from app.models.maintenance import MaintenanceRecord, MaintenanceStatus
from app.models.tool import DepreciationMethod, Tool, ToolStatus
from app.models.toolbox import Toolbox, ToolboxItem
from app.models.toolbox_audit import AuditItemCondition, ToolboxAudit, ToolboxAuditItem, ToolboxAuditStatus
from app.models.user import User, UserRole
from app.services.maintenance_service import send_tool_to_maintenance
from app.services.pdf_service import generate_loan_voucher
from app.services.qr_service import generate_tool_qr, generate_toolbox_qr

# Marca/Categoría/Ubicación/Proveedor de las tablas maestras (Fase 2) —
# a propósito son EXACTAMENTE los mismos valores que usan las herramientas
# de abajo, para que los desplegables del formulario ya tengan cargado
# todo lo que aparece en los datos de ejemplo (si no, el dropdown queda
# vacío aunque las herramientas ya tengan marca/categoría/ubicación).
BRANDS = ["Bosch", "Makita", "Stanley", "Gedore", "Mitutoyo", "Fluke", "Schulz", "Ingersoll Rand", "DeWalt"]
CATEGORIES = ["Eléctricas", "Manuales", "Medición", "Neumáticas"]
LOCATIONS = [
    "Estante A1", "Estante B2", "Estante C1", "Taller — banco 2",
    "Depósito trasero", "Baja — pendiente descarte",
]
# Incluye tanto los proveedores de COMPRA (los que traen la herramienta
# nueva) como los talleres de SERVICIO TÉCNICO que se usan en Mantenimiento
# — es el mismo desplegable en las dos pantallas (GET /api/v1/lookups/providers).
PROVIDERS = [
    "Casa Bagnara", "Ferretería Central", "Instrumentos SRL", "Neumática del Sur",
    "Fluke Service Chile", "Taller de Motores del Sur",
]

TOOLS = [
    dict(name="Taladro Percutor", brand="Bosch", model="GSB 13 RE", serial_number="TL-0001",
         category="Eléctricas", location="Estante A1", supplier="Casa Bagnara",
         purchase_date=date.today() - timedelta(days=400), purchase_cost=Decimal("45000"),
         salvage_value=Decimal("4500"), useful_life_years=5, depreciation_method=DepreciationMethod.lineal,
         status=ToolStatus.disponible),
    dict(name='Amoladora Angular 7"', brand="Makita", model="GA9020", serial_number="TL-0002",
         category="Eléctricas", location="Estante A1", supplier="Casa Bagnara",
         purchase_date=date.today() - timedelta(days=200), purchase_cost=Decimal("38000"),
         salvage_value=Decimal("3800"), useful_life_years=5, depreciation_method=DepreciationMethod.lineal,
         status=ToolStatus.prestado),
    dict(name="Martillo de Bola", brand="Stanley", model=None, serial_number="TL-0003",
         category="Manuales", location="Estante B2", supplier="Ferretería Central",
         purchase_date=date.today() - timedelta(days=900), purchase_cost=Decimal("8000"),
         salvage_value=Decimal("800"), useful_life_years=8, depreciation_method=DepreciationMethod.lineal,
         status=ToolStatus.disponible),
    dict(name="Juego de Llaves Combinadas", brand="Gedore", model="8-19mm", serial_number="TL-0004",
         category="Manuales", location="Estante B2", supplier="Ferretería Central",
         purchase_date=date.today() - timedelta(days=600), purchase_cost=Decimal("25000"),
         salvage_value=Decimal("2500"), useful_life_years=10, depreciation_method=DepreciationMethod.lineal,
         status=ToolStatus.disponible),
    dict(name="Calibre Digital", brand="Mitutoyo", model="500-196-30", serial_number="TL-0005",
         category="Medición", location="Estante C1", supplier="Instrumentos SRL",
         purchase_date=date.today() - timedelta(days=300), purchase_cost=Decimal("60000"),
         salvage_value=Decimal("6000"), useful_life_years=6, depreciation_method=DepreciationMethod.doble_saldo,
         status=ToolStatus.disponible),
    # En mantenimiento — el registro que explica el motivo se crea más abajo,
    # después de tener el usuario Encargado (MaintenanceRecord.created_by).
    dict(name="Multímetro Digital", brand="Fluke", model="115", serial_number="TL-0006",
         category="Medición", location="Taller — banco 2", supplier="Instrumentos SRL",
         purchase_date=date.today() - timedelta(days=500), purchase_cost=Decimal("55000"),
         salvage_value=Decimal("5500"), useful_life_years=6, depreciation_method=DepreciationMethod.lineal,
         status=ToolStatus.mantenimiento, description="En revisión — pantalla intermitente"),
    dict(name="Compresor de Aire 50L", brand="Schulz", model="CSI 10", serial_number="TL-0007",
         category="Neumáticas", location="Depósito trasero", supplier="Neumática del Sur",
         purchase_date=date.today() - timedelta(days=800), purchase_cost=Decimal("180000"),
         salvage_value=Decimal("18000"), useful_life_years=10, depreciation_method=DepreciationMethod.lineal,
         status=ToolStatus.disponible),
    dict(name="Pistola de Impacto Neumática", brand="Ingersoll Rand", model="231C", serial_number="TL-0008",
         category="Neumáticas", location="Depósito trasero", supplier="Neumática del Sur",
         purchase_date=date.today() - timedelta(days=150), purchase_cost=Decimal("95000"),
         salvage_value=Decimal("9500"), useful_life_years=6, depreciation_method=DepreciationMethod.lineal,
         status=ToolStatus.prestado),
    # Dada de baja — igual que arriba, el MaintenanceRecord (sin_solucion)
    # que justifica la baja se crea más abajo, y ahí también se completan
    # decommission_reason/decommission_date/decommission_authorized_by_id
    # (Fase 3), que acá quedarían vacíos si no se completan a mano.
    dict(name="Sierra Circular", brand="DeWalt", model="DWE575", serial_number="TL-0009",
         category="Eléctricas", location="Baja — pendiente descarte", supplier="Casa Bagnara",
         purchase_date=date.today() - timedelta(days=1800), purchase_cost=Decimal("42000"),
         salvage_value=Decimal("0"), useful_life_years=5, depreciation_method=DepreciationMethod.lineal,
         status=ToolStatus.baja, description="Motor quemado, dada de baja"),
    # Estas dos últimas nacen directamente "en_caja" (Fase 2): van a la caja
    # de herramientas de abajo, así que nunca pasan por "disponible" en
    # este set de ejemplo — igual que quedarían en la app real apenas se
    # arma la caja.
    dict(name="Nivel Láser", brand="Bosch", model="GLL 3-80", serial_number="TL-0010",
         category="Medición", location="Estante C1", supplier="Instrumentos SRL",
         purchase_date=date.today() - timedelta(days=100), purchase_cost=Decimal("32000"),
         salvage_value=Decimal("3200"), useful_life_years=6, depreciation_method=DepreciationMethod.lineal,
         status=ToolStatus.en_caja),
    dict(name="Set Destornilladores de Precisión", brand="Stanley", model="STHT0-62143", serial_number="TL-0011",
         category="Manuales", location="Estante C1", supplier="Ferretería Central",
         purchase_date=date.today() - timedelta(days=250), purchase_cost=Decimal("12000"),
         salvage_value=Decimal("1200"), useful_life_years=5, depreciation_method=DepreciationMethod.lineal,
         status=ToolStatus.en_caja),
]


async def _get_or_create(db: AsyncSession, model, name: str, **extra):
    """Trae la fila del catálogo por nombre o la crea si todavía no existe."""
    existing = (await db.execute(select(model).where(model.name == name))).scalar_one_or_none()
    if existing:
        return existing
    row = model(name=name, **extra)
    db.add(row)
    await db.flush()
    return row


async def main() -> None:
    await create_tables()
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(func.count()).select_from(Tool))).scalar_one()
        if existing > 0:
            print("⏭  Ya hay herramientas cargadas — no se agregan datos de ejemplo de nuevo.")
            print("   (si querés recargar desde cero, vaciá la base primero)")
            return

        jefe = (await db.execute(select(User).where(User.role == UserRole.jefe))).scalars().first()
        encargado = (await db.execute(select(User).where(User.role == UserRole.encargado))).scalars().first()
        mecanico = (await db.execute(select(User).where(User.role == UserRole.mecanico))).scalars().first()
        if not jefe or not encargado or not mecanico:
            print("❌ Faltan los usuarios base — corré primero: python scripts/seed_data.py")
            return

        # --- Tablas maestras (Fase 2) ---
        for name in BRANDS:
            await _get_or_create(db, Brand, name)
        for name in CATEGORIES:
            await _get_or_create(db, Category, name)
        for name in LOCATIONS:
            await _get_or_create(db, Location, name)
        for name in PROVIDERS:
            await _get_or_create(db, Provider, name)
        await db.commit()
        print(f"✅ Tablas maestras: {len(BRANDS)} marcas, {len(CATEGORIES)} categorías, "
              f"{len(LOCATIONS)} ubicaciones, {len(PROVIDERS)} proveedores")

        # --- Herramientas ---
        tools_by_serial = {}
        for data in TOOLS:
            tool = Tool(**data)
            db.add(tool)
            await db.flush()
            tool.qr_code_url = generate_tool_qr(tool.id)
            tools_by_serial[data["serial_number"]] = tool
            print(f"✅ Herramienta: {tool.name} ({tool.status.value})")
        await db.commit()

        # --- Mantenimiento (Fase 3) ---
        # Multímetro: todavía en curso — el motivo por el que está "en
        # mantenimiento" en vez de flotar como un estado sin explicación.
        multimetro = tools_by_serial["TL-0006"]
        db.add(MaintenanceRecord(
            tool_id=multimetro.id, provider="Fluke Service Chile",
            reason="Pantalla intermitente, posible falla del flex interno",
            status=MaintenanceStatus.en_proceso,
            sent_date=date.today() - timedelta(days=10),
            created_by_id=encargado.id,
        ))
        print(f"✅ Mantenimiento en curso: {multimetro.name} → Fluke Service Chile")

        # Sierra Circular: la historia completa detrás de la baja —
        # se mandó a mantenimiento, no tuvo arreglo posible, y por eso
        # se dio de baja (no una baja "de la nada").
        sierra = tools_by_serial["TL-0009"]
        db.add(MaintenanceRecord(
            tool_id=sierra.id, provider="Taller de Motores del Sur",
            reason="Motor quemado, no arranca",
            status=MaintenanceStatus.sin_solucion,
            sent_date=date.today() - timedelta(days=60),
            resolved_date=date.today() - timedelta(days=45),
            resolution_notes="Bobinado quemado — el costo de repuesto supera el valor de reposición de la herramienta.",
            created_by_id=encargado.id,
        ))
        sierra.decommission_reason = "Motor quemado sin reparación viable (ver historial de mantenimiento)."
        sierra.decommission_date = date.today() - timedelta(days=40)
        sierra.decommission_authorized_by_id = jefe.id
        print(f"✅ Mantenimiento sin solución + baja: {sierra.name} (autorizó: {jefe.full_name})")
        await db.commit()

        # --- Préstamos ---
        amoladora = tools_by_serial["TL-0002"]
        pistola = tools_by_serial["TL-0008"]
        taladro = tools_by_serial["TL-0001"]

        loan_active = Loan(
            tool_id=amoladora.id, borrower_id=mecanico.id, issued_by_id=jefe.id,
            due_date=date.today() + timedelta(days=3), status=LoanStatus.activo,
            purpose="Obra en taller 2",
        )
        db.add(loan_active)
        await db.flush()
        loan_active.voucher_pdf_url = generate_loan_voucher(loan_active, amoladora, mecanico, jefe)
        print(f"✅ Préstamo activo: {amoladora.name} → {mecanico.full_name} (vence en 3 días)")

        loan_overdue = Loan(
            tool_id=pistola.id, borrower_id=mecanico.id, issued_by_id=jefe.id,
            due_date=date.today() - timedelta(days=5), status=LoanStatus.vencido,
            purpose="Cambio de neumáticos", alert_sent=True,
        )
        db.add(loan_overdue)
        await db.flush()
        loan_overdue.voucher_pdf_url = generate_loan_voucher(loan_overdue, pistola, mecanico, jefe)
        print(f"✅ Préstamo VENCIDO: {pistola.name} → {mecanico.full_name} (venció hace 5 días)")

        loan_returned = Loan(
            tool_id=taladro.id, borrower_id=mecanico.id, issued_by_id=jefe.id,
            due_date=date.today() - timedelta(days=20), status=LoanStatus.devuelto,
            return_date=date.today() - timedelta(days=18), return_condition=ReturnCondition.bueno,
            purpose="Instalación eléctrica",
        )
        db.add(loan_returned)
        print(f"✅ Préstamo ya devuelto (histórico): {taladro.name}")
        await db.commit()

        # --- Caja de herramientas, con mecánico responsable (Fase 1) ---
        toolbox = Toolbox(
            name="Caja Electricista", location="Depósito A",
            description="Herramientas para trabajos eléctricos de rutina",
            responsible_user_id=mecanico.id,
        )
        db.add(toolbox)
        await db.flush()
        toolbox.qr_code_url = generate_toolbox_qr(toolbox.id)

        nivel = tools_by_serial["TL-0010"]
        destornilladores = tools_by_serial["TL-0011"]
        db.add(ToolboxItem(toolbox_id=toolbox.id, tool_id=nivel.id))
        db.add(ToolboxItem(toolbox_id=toolbox.id, tool_id=destornilladores.id))
        await db.commit()
        print(f'✅ Caja "{toolbox.name}" (responsable: {mecanico.full_name}) con: '
              f'{nivel.name}, {destornilladores.name}')

        # --- Auditoría de caja completada (Fase 4), con un ítem que se
        # detecta dañado y se manda a mantenimiento desde la propia
        # auditoría — el mismo flujo que la pantalla de Cajas ejecuta al
        # tocar "Enviar a mantenimiento" en un ítem dañado.
        audit = ToolboxAudit(
            toolbox_id=toolbox.id,
            audit_date=date.today() - timedelta(days=2),
            performed_by_id=encargado.id,
            status=ToolboxAuditStatus.completado,
            notes="Auditoría mensual de rutina.",
            created_at=datetime.utcnow() - timedelta(days=2, hours=1),
            completed_at=datetime.utcnow() - timedelta(days=2),
        )
        db.add(audit)
        await db.flush()

        item_ok = ToolboxAuditItem(
            audit_id=audit.id, tool_id=nivel.id,
            condition=AuditItemCondition.bueno,
            reviewed_at=datetime.utcnow() - timedelta(days=2),
        )
        item_danado = ToolboxAuditItem(
            audit_id=audit.id, tool_id=destornilladores.id,
            condition=AuditItemCondition.dañado,
            observation="Mango de una de las puntas rota.",
            reviewed_at=datetime.utcnow() - timedelta(days=2),
        )
        db.add_all([item_ok, item_danado])
        await db.flush()

        await send_tool_to_maintenance(
            db, tool=destornilladores, provider="Ferretería Central",
            reason="Mango de una punta rota — detectado en auditoría de caja",
            user=encargado, ip_address=None,
            extra_detail=f"Detectado durante la auditoría de la caja '{toolbox.name}'.",
        )
        item_danado.sent_to_maintenance = True
        await db.commit()
        print(f'✅ Auditoría completada de "{toolbox.name}": 1 ítem bueno, '
              f'1 dañado → enviado a mantenimiento (Ferretería Central)')


if __name__ == "__main__":
    asyncio.run(main())
    print("\n🧰 Datos de ejemplo cargados correctamente.")
