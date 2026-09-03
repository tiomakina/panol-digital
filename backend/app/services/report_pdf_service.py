"""
Generación de PDFs para los reportes del sistema — Inventario, Préstamos y
Mantenimiento. Usa la misma librería (reportlab) que los vales de préstamo,
aplicando el branding dinámico de la empresa (color primario + nombre).
"""
import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.branding import load_brand_config


def _hex_to_rgb(hex_color: str):
    """Convierte #rrggbb a un Color de reportlab."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    return colors.Color(r, g, b)


def _brand_color() -> colors.Color:
    brand = load_brand_config()
    try:
        return _hex_to_rgb(brand.get("primary_color", "#4f46e5"))
    except Exception:
        return colors.HexColor("#4f46e5")


def _company_name() -> str:
    brand = load_brand_config()
    return brand.get("company_name", "Pañol 360")


def _header_table(title: str, subtitle: str) -> Table:
    """Encabezado con nombre empresa + título + fecha."""
    company = _company_name()
    today = date.today().strftime("%d/%m/%Y")
    data = [[f"Pañol 360  ·  {company}", title, f"Generado: {today}  ·  Pañol 360"]]
    t = Table(data, colWidths=["30%", "40%", "30%"])
    bc = _brand_color()
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), bc),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("LEFTPADDING", (0, 0), (0, 0), 8),
                ("RIGHTPADDING", (2, 0), (2, 0), 8),
            ]
        )
    )
    return t


def _footer_table(summary_text: str) -> Table:
    data = [[summary_text]]
    t = Table(data, colWidths=["100%"])
    bc = _brand_color()
    light = colors.Color(bc.red, bc.green, bc.blue, alpha=0.1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), light),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return t


def _data_table(headers: list[str], rows: list[list]) -> Table:
    """Tabla de datos con encabezado coloreado y filas alternadas."""
    bc = _brand_color()
    light = colors.Color(bc.red, bc.green, bc.blue, alpha=0.08)

    data = [headers] + rows
    # Distribuye el ancho total de la página menos márgenes (~257mm en landscape A4)
    col_count = len(headers)
    col_width = 257 * mm / col_count
    t = Table(data, colWidths=[col_width] * col_count, repeatRows=1)

    style = [
        # Encabezado
        ("BACKGROUND", (0, 0), (-1, 0), bc),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        # Cuerpo
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 7),
        ("ALIGN", (0, 1), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        # Grid
        ("GRID", (0, 0), (-1, -1), 0.3, colors.Color(0.8, 0.8, 0.8)),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, bc),
    ]
    # Filas alternadas
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), light))
    t.setStyle(TableStyle(style))
    return t


# ─────────────────────────────────────────────────────────────────────────────
# PDFs públicos
# ─────────────────────────────────────────────────────────────────────────────

def generate_inventory_pdf(rows: list[dict]) -> bytes:
    """
    PDF de inventario valorizado — una fila por herramienta con estado,
    ubicación, costo de compra y valor en libros actual.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    def _fmt_money(v) -> str:
        if v is None:
            return "—"
        return f"${v:,.0f}"

    headers = ["Nombre", "Marca", "Categoría", "Serie", "Estado", "Ubicación", "Costo compra", "Valor actual"]
    data_rows = [
        [
            r["name"] or "—",
            r["brand"] or "—",
            r["category"] or "—",
            r["serial_number"] or "—",
            r["status"] or "—",
            r["location"] or "—",
            _fmt_money(r["purchase_cost"]),
            _fmt_money(r["current_value"]),
        ]
        for r in rows
    ]

    total_cost = sum(r["purchase_cost"] or 0 for r in rows)
    total_value = sum(r["current_value"] or 0 for r in rows)
    summary = (
        f"Total herramientas: {len(rows)}    "
        f"Costo total: {_fmt_money(total_cost)}    "
        f"Valor en libros: {_fmt_money(total_value)}"
    )

    story = [
        _header_table("Reporte de Inventario", f"Al {date.today().strftime('%d/%m/%Y')}"),
        Spacer(1, 4 * mm),
        _data_table(headers, data_rows),
        Spacer(1, 3 * mm),
        _footer_table(summary),
    ]
    doc.build(story)
    return buf.getvalue()


def generate_loans_pdf(rows: list[dict]) -> bytes:
    """PDF del historial de préstamos con estado y responsable."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    def _fmt_date(d) -> str:
        return d[:10] if d else "—"

    def _status_label(s: str) -> str:
        return {
            "activo": "Activo",
            "devuelto": "Devuelto",
            "vencido": "Vencido",
        }.get(s, s)

    headers = ["#", "Herramienta", "Categoría", "Responsable", "Fecha préstamo", "Vencimiento", "Devolución", "Estado"]
    data_rows = [
        [
            str(r["id"]),
            r["tool"] or "—",
            r["tool_category"] or "—",
            r["borrower"] or "—",
            _fmt_date(r["loan_date"]),
            _fmt_date(r["due_date"]),
            _fmt_date(r["return_date"]),
            _status_label(r["status"]),
        ]
        for r in rows
    ]

    activos = sum(1 for r in rows if r["status"] == "activo")
    vencidos = sum(1 for r in rows if r["status"] == "vencido")
    devueltos = sum(1 for r in rows if r["status"] == "devuelto")
    summary = (
        f"Total: {len(rows)}    "
        f"Activos: {activos}    "
        f"Vencidos: {vencidos}    "
        f"Devueltos: {devueltos}"
    )

    story = [
        _header_table("Reporte de Préstamos", f"Al {date.today().strftime('%d/%m/%Y')}"),
        Spacer(1, 4 * mm),
        _data_table(headers, data_rows),
        Spacer(1, 3 * mm),
        _footer_table(summary),
    ]
    doc.build(story)
    return buf.getvalue()


def generate_maintenance_pdf(rows: list[dict]) -> bytes:
    """PDF del historial de mantenimiento con costos y estado."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    def _fmt_date(d) -> str:
        return d[:10] if d else "—"

    def _fmt_money(v) -> str:
        if v is None:
            return "—"
        return f"${float(v):,.0f}"

    def _status_label(s: str) -> str:
        return {
            "en_proceso": "En proceso",
            "completado": "Completado",
            "cancelado": "Cancelado",
        }.get(s, s)

    headers = ["#", "Herramienta", "Título", "Técnico", "Fecha envío", "Fecha retorno", "Costo", "Estado"]
    data_rows = [
        [
            str(r.get("id", "")),
            r.get("tool_name") or "—",
            (r.get("title") or "Sin título")[:40],
            r.get("technician") or "—",
            _fmt_date(r.get("sent_date")),
            _fmt_date(r.get("return_date")),
            _fmt_money(r.get("cost")),
            _status_label(r.get("status", "")),
        ]
        for r in rows
    ]

    total_cost = sum(float(r.get("cost") or 0) for r in rows)
    summary = (
        f"Total registros: {len(rows)}    "
        f"Costo total: ${total_cost:,.0f}"
    )

    story = [
        _header_table("Reporte de Mantenimiento", f"Al {date.today().strftime('%d/%m/%Y')}"),
        Spacer(1, 4 * mm),
        _data_table(headers, data_rows),
        Spacer(1, 3 * mm),
        _footer_table(summary),
    ]
    doc.build(story)
    return buf.getvalue()
