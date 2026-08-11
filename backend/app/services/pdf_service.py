"""
Servicio de generación de Vales PDF — comprobante de préstamo con los datos
de la herramienta, el responsable y la firma digital táctil, con el branding
de la empresa aplicado (color primario y nombre de la empresa).
"""
import base64
import io
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.core.branding import load_brand_config
from app.core.config import settings
from app.models.loan import Loan
from app.models.tool import Tool
from app.models.user import User

VOUCHER_DIR = Path(settings.UPLOAD_DIR) / "vouchers"


def _decode_signature(signature_data: str) -> ImageReader | None:
    """Decodifica la firma digital (dataURL base64 capturada en pantalla táctil) a imagen."""
    try:
        if "," in signature_data:
            signature_data = signature_data.split(",", 1)[1]
        img_bytes = base64.b64decode(signature_data)
        return ImageReader(io.BytesIO(img_bytes))
    except Exception:
        return None


def generate_loan_voucher(loan: Loan, tool: Tool, borrower: User, issued_by: User) -> str:
    """
    Genera el vale PDF de un préstamo (datos de herramienta, responsable y firma
    digital si fue capturada) y lo guarda en app/static/uploads/vouchers/.
    Devuelve la URL pública del PDF.
    """
    brand = load_brand_config()
    VOUCHER_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"vale_{loan.id}.pdf"
    filepath = VOUCHER_DIR / filename

    c = canvas.Canvas(str(filepath), pagesize=A5)
    width, height = A5
    primary = colors.HexColor(brand.get("primary_color", "#4f46e5"))

    # Encabezado con branding de la empresa
    c.setFillColor(primary)
    c.rect(0, height - 25 * mm, width, 25 * mm, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(10 * mm, height - 12 * mm, brand.get("company_name", "Pañol"))
    c.setFont("Helvetica", 9)
    c.drawString(10 * mm, height - 18 * mm, "Vale de Préstamo de Herramienta")

    y = height - 35 * mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(10 * mm, y, f"Vale N° {loan.id:06d}")
    c.setFont("Helvetica", 9)
    c.drawString(10 * mm, y - 6 * mm, f"Fecha de emisión: {loan.loan_date.strftime('%d/%m/%Y %H:%M')}")
    c.drawString(10 * mm, y - 11 * mm, f"Fecha de devolución prevista: {loan.due_date.strftime('%d/%m/%Y')}")

    y -= 22 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(10 * mm, y, "Herramienta")
    c.setFont("Helvetica", 9)
    tool_line = tool.name + (f" — {tool.brand}" if tool.brand else "")
    c.drawString(10 * mm, y - 6 * mm, tool_line)
    if tool.serial_number:
        c.drawString(10 * mm, y - 11 * mm, f"N° de serie: {tool.serial_number}")

    y -= 22 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(10 * mm, y, "Responsable")
    c.setFont("Helvetica", 9)
    c.drawString(10 * mm, y - 6 * mm, borrower.full_name)
    c.drawString(10 * mm, y - 11 * mm, borrower.email)
    if loan.purpose:
        c.drawString(10 * mm, y - 16 * mm, f"Motivo: {loan.purpose}")

    y -= 26 * mm
    c.setFont("Helvetica", 8)
    c.drawString(10 * mm, y, f"Entregado por: {issued_by.full_name}")

    # Firma digital táctil
    y -= 30 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(10 * mm, y + 22 * mm, "Firma del responsable")
    c.setStrokeColor(colors.grey)
    c.rect(10 * mm, y, width - 20 * mm, 20 * mm, fill=False)
    if loan.signature_data:
        signature_img = _decode_signature(loan.signature_data)
        if signature_img:
            c.drawImage(
                signature_img,
                12 * mm, y + 1 * mm,
                width=width - 24 * mm, height=18 * mm,
                preserveAspectRatio=True, mask="auto",
            )

    c.setFont("Helvetica-Oblique", 7)
    c.setFillColor(colors.grey)
    c.drawString(10 * mm, 8 * mm, f"Generado electrónicamente el {datetime.utcnow().strftime('%d/%m/%Y %H:%M UTC')}")

    c.showPage()
    c.save()

    return f"/static/uploads/vouchers/{filename}"
