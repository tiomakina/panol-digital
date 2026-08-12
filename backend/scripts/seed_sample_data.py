"""
Script de datos de EJEMPLO — herramientas, préstamos y una caja realistas
para probar el sistema con algo más que una base vacía.

Requiere que ya corriste `python scripts/seed_data.py` (los 3 usuarios base).
Es idempotente: si ya hay herramientas cargadas, no hace nada (para no
duplicar datos en cada corrida).

Uso: docker-compose exec backend python scripts/seed_sample_data.py
     (o `python scripts/seed_sample_data.py` desde backend/ en desarrollo local)
"""
import asyncio
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal, create_tables
from app.models.loan import Loan, LoanStatus, ReturnCondition
from app.models.tool import DepreciationMethod, Tool, ToolStatus
from app.models.toolbox import Toolbox, ToolboxItem
from app.models.user import User, UserRole
from app.services.pdf_service import generate_loan_voucher
from app.services.qr_service import generate_tool_qr, generate_toolbox_qr

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
    dict(name="Sierra Circular", brand="DeWalt", model="DWE575", serial_number="TL-0009",
         category="Eléctricas", location="Baja — pendiente descarte", supplier="Casa Bagnara",
         purchase_date=date.today() - timedelta(days=1800), purchase_cost=Decimal("42000"),
         salvage_value=Decimal("0"), useful_life_years=5, depreciation_method=DepreciationMethod.lineal,
         status=ToolStatus.baja, description="Motor quemado, dada de baja"),
    dict(name="Nivel Láser", brand="Bosch", model="GLL 3-80", serial_number="TL-0010",
         category="Medición", location="Estante C1", supplier="Instrumentos SRL",
         purchase_date=date.today() - timedelta(days=100), purchase_cost=Decimal("32000"),
         salvage_value=Decimal("3200"), useful_life_years=6, depreciation_method=DepreciationMethod.lineal,
         status=ToolStatus.disponible),
]


async def main() -> None:
    await create_tables()
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(func.count()).select_from(Tool))).scalar_one()
        if existing > 0:
            print("⏭  Ya hay herramientas cargadas — no se agregan datos de ejemplo de nuevo.")
            print("   (si querés recargar desde cero, vaciá la base primero)")
            return

        jefe = (await db.execute(select(User).where(User.role == UserRole.jefe))).scalars().first()
        mecanico = (await db.execute(select(User).where(User.role == UserRole.mecanico))).scalars().first()
        if not jefe or not mecanico:
            print("❌ Faltan los usuarios base — corré primero: python scripts/seed_data.py")
            return

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

        # --- Caja de herramientas ---
        toolbox = Toolbox(name="Caja Electricista", location="Depósito A",
                           description="Herramientas para trabajos eléctricos de rutina")
        db.add(toolbox)
        await db.flush()
        toolbox.qr_code_url = generate_toolbox_qr(toolbox.id)

        nivel = tools_by_serial["TL-0010"]
        db.add(ToolboxItem(toolbox_id=toolbox.id, tool_id=nivel.id))
        print(f'✅ Caja "{toolbox.name}" con: {nivel.name}')

        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
    print("\n🧰 Datos de ejemplo cargados correctamente.")
