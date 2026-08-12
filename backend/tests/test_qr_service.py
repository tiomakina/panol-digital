"""Pruebas del servicio de generación/lectura de códigos QR."""
import os

from app.core.config import settings
from app.services.qr_service import decode_qr_payload, generate_tool_qr


def test_generate_and_read_qr_file():
    url = generate_tool_qr(12345, base_url="http://localhost:8000")
    assert url == "/static/uploads/qr/tool_12345.png"

    file_path = os.path.join(settings.UPLOAD_DIR, "qr", "tool_12345.png")
    assert os.path.exists(file_path)


def test_decode_qr_payload_variants():
    assert decode_qr_payload("panol://tool/7") == 7
    assert decode_qr_payload("http://localhost:8000/tools/42") == 42
    assert decode_qr_payload("no-es-un-codigo-valido") is None
