"""
Servicio de import/export masivo de herramientas por CSV.

El export siempre incluye TODAS las columnas editables de Tool. El import
matchea por número de serie: si ya existe una herramienta con ese
serial_number, la actualiza (sin tocar su status — eso lo maneja el flujo
normal de la app, no una planilla); si no, crea una nueva con
status=disponible. Los valores de marca/categoría/ubicación/proveedor que
no existan todavía en las tablas maestras se dan de alta automáticamente,
para que el desplegable del formulario los tenga disponibles después.
"""
import csv
import io
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lookup import Brand, Category, Location, Provider
from app.models.tool import DepreciationMethod, Tool, ToolStatus

CSV_COLUMNS = [
    "name", "brand", "model", "serial_number", "category", "location", "supplier",
    "status", "purchase_date", "purchase_cost", "salvage_value", "useful_life_years",
    "depreciation_method", "description",
]

# Status que se pueden asignar por planilla — el resto (prestado, en_caja)
# solo los debe manejar la app a través de sus propios flujos (préstamos,
# cajas), nunca una carga masiva.
_IMPORTABLE_STATUSES = {ToolStatus.disponible, ToolStatus.mantenimiento, ToolStatus.baja}


def tools_to_csv(tools: list[Tool]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for t in tools:
        writer.writerow({
            "name": t.name,
            "brand": t.brand or "",
            "model": t.model or "",
            "serial_number": t.serial_number or "",
            "category": t.category or "",
            "location": t.location or "",
            "supplier": t.supplier or "",
            "status": t.status.value,
            "purchase_date": t.purchase_date.isoformat() if t.purchase_date else "",
            "purchase_cost": str(t.purchase_cost) if t.purchase_cost is not None else "",
            "salvage_value": str(t.salvage_value) if t.salvage_value is not None else "",
            "useful_life_years": t.useful_life_years if t.useful_life_years is not None else "",
            "depreciation_method": t.depreciation_method.value if t.depreciation_method else "",
            "description": t.description or "",
        })
    # BOM al principio para que Excel abra el UTF-8 sin romper acentos/ñ.
    return ("﻿" + buf.getvalue()).encode("utf-8")


@dataclass
class ImportRowError:
    row: int
    detail: str


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    errors: list[ImportRowError] = field(default_factory=list)


def _parse_decimal(value: str, field_name: str, row_num: int) -> Decimal | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        raise ValueError(f"'{field_name}' inválido: '{value}'")


def _parse_date(value: str, field_name: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"'{field_name}' debe tener formato AAAA-MM-DD, recibí '{value}'")


async def _upsert_lookup(db: AsyncSession, model, name: str, seen: set[str]) -> None:
    name = (name or "").strip()
    if not name or name in seen:
        return
    seen.add(name)
    existing = await db.execute(select(model).where(model.name == name))
    if existing.scalar_one_or_none() is None:
        db.add(model(name=name))


async def parse_and_import_tools_csv(db: AsyncSession, file_bytes: bytes) -> ImportResult:
    result = ImportResult()

    try:
        text = file_bytes.decode("utf-8-sig")  # utf-8-sig traga el BOM si vino de Excel
    except UnicodeDecodeError:
        result.errors.append(ImportRowError(row=0, detail="El archivo no está en UTF-8"))
        return result

    reader = csv.DictReader(io.StringIO(text))
    missing_cols = {"name"} - set(reader.fieldnames or [])
    if missing_cols:
        result.errors.append(ImportRowError(row=0, detail="Falta la columna obligatoria 'name' en el CSV"))
        return result

    seen_brands: set[str] = set()
    seen_categories: set[str] = set()
    seen_locations: set[str] = set()
    seen_providers: set[str] = set()
    # Herramientas creadas EN ESTE MISMO import, indexadas por número de
    # serie — sin esto, dos filas del archivo con el mismo serial_number
    # intentarían insertar dos filas con la misma clave única y el import
    # entero volaría con un error de integridad recién al hacer commit.
    pending_by_serial: dict[str, Tool] = {}

    for row_num, row in enumerate(reader, start=2):  # fila 1 es el encabezado
        name = (row.get("name") or "").strip()
        if not name:
            result.errors.append(ImportRowError(row=row_num, detail="Falta el nombre de la herramienta"))
            continue

        try:
            purchase_cost = _parse_decimal(row.get("purchase_cost", ""), "purchase_cost", row_num)
            salvage_value = _parse_decimal(row.get("salvage_value", ""), "salvage_value", row_num)
            purchase_date = _parse_date(row.get("purchase_date", ""), "purchase_date")

            useful_life_raw = (row.get("useful_life_years") or "").strip()
            useful_life_years = int(useful_life_raw) if useful_life_raw else None

            depreciation_raw = (row.get("depreciation_method") or "").strip()
            depreciation_method = DepreciationMethod(depreciation_raw) if depreciation_raw else None

            status_raw = (row.get("status") or "").strip()
            new_status = None
            if status_raw:
                try:
                    new_status = ToolStatus(status_raw)
                except ValueError:
                    raise ValueError(f"'status' inválido: '{status_raw}'")
                if new_status not in _IMPORTABLE_STATUSES:
                    raise ValueError(
                        f"'status' no se puede cargar por planilla: '{status_raw}' "
                        f"(solo disponible/mantenimiento/baja)"
                    )
        except ValueError as exc:
            result.errors.append(ImportRowError(row=row_num, detail=str(exc)))
            continue

        serial_number = (row.get("serial_number") or "").strip() or None
        brand = (row.get("brand") or "").strip() or None
        category = (row.get("category") or "").strip() or None
        location = (row.get("location") or "").strip() or None
        supplier = (row.get("supplier") or "").strip() or None

        existing_tool = None
        if serial_number:
            existing_tool = pending_by_serial.get(serial_number)
            if existing_tool is None:
                existing = await db.execute(select(Tool).where(Tool.serial_number == serial_number))
                existing_tool = existing.scalar_one_or_none()

        if existing_tool:
            existing_tool.name = name
            existing_tool.brand = brand
            existing_tool.model = (row.get("model") or "").strip() or None
            existing_tool.category = category
            existing_tool.location = location
            existing_tool.supplier = supplier
            existing_tool.description = (row.get("description") or "").strip() or None
            if purchase_date is not None:
                existing_tool.purchase_date = purchase_date
            if purchase_cost is not None:
                existing_tool.purchase_cost = purchase_cost
            if salvage_value is not None:
                existing_tool.salvage_value = salvage_value
            if useful_life_years is not None:
                existing_tool.useful_life_years = useful_life_years
            if depreciation_method is not None:
                existing_tool.depreciation_method = depreciation_method
            # El status de una herramienta existente solo se toca si vino
            # explícito en la fila — no queremos que reimportar el mismo
            # CSV "pise" un préstamo o mantenimiento en curso.
            if new_status is not None:
                existing_tool.status = new_status
            result.updated += 1
        else:
            new_tool = Tool(
                name=name,
                brand=brand,
                model=(row.get("model") or "").strip() or None,
                serial_number=serial_number,
                category=category,
                location=location,
                supplier=supplier,
                status=new_status or ToolStatus.disponible,
                purchase_date=purchase_date,
                purchase_cost=purchase_cost,
                salvage_value=salvage_value if salvage_value is not None else Decimal("0"),
                useful_life_years=useful_life_years if useful_life_years is not None else 5,
                depreciation_method=depreciation_method or DepreciationMethod.lineal,
                description=(row.get("description") or "").strip() or None,
            )
            db.add(new_tool)
            if serial_number:
                pending_by_serial[serial_number] = new_tool
            result.created += 1

        await _upsert_lookup(db, Brand, brand, seen_brands)
        await _upsert_lookup(db, Category, category, seen_categories)
        await _upsert_lookup(db, Location, location, seen_locations)
        await _upsert_lookup(db, Provider, supplier, seen_providers)

    return result
