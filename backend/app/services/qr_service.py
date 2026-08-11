"""
Servicio de Códigos QR — genera y resuelve los QR de inventario que se
escanean con la cámara del dispositivo (ver qr-scanner.js en el frontend).
"""
import io
from pathlib import Path
import qrcode
from app.core.config import settings

QR_DIR = Path(settings.UPLOAD_DIR) / "qr"


def generate_tool_qr(tool_id: int, base_url: str = "") -> str:
    """
    Genera el código QR de una herramienta apuntando a su ficha y lo guarda
    como PNG en app/static/uploads/qr/tool_{id}.png. Devuelve la URL pública.
    """
    payload = f"{base_url}/tools/{tool_id}" if base_url else f"panol://tool/{tool_id}"

    img = qrcode.make(payload)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")

    QR_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"tool_{tool_id}.png"
    with open(QR_DIR / filename, "wb") as f:
        f.write(buffer.getvalue())

    return f"/static/uploads/qr/{filename}"


def decode_qr_payload(data: str) -> int | None:
    """Extrae el ID de herramienta desde el contenido leído por el escáner QR."""
    data = data.strip()
    if data.startswith("panol://tool/"):
        suffix = data.rsplit("/", 1)[-1]
    elif "/tools/" in data:
        suffix = data.rsplit("/tools/", 1)[-1]
    else:
        suffix = data
    return int(suffix) if suffix.isdigit() else None
