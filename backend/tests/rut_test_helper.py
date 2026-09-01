"""
Helper compartido SOLO para generar RUTs ficticios pero válidos en los
tests (no es un helper de negocio como _create_user/_login, que cada
archivo de test mantiene local a propósito — esto es puro plumbing para
no reimplementar el hash en cada archivo).
"""
import hashlib

from app.core.rut import compute_check_digit


def fake_rut(seed: str) -> str:
    """RUT determinístico a partir de un string (ej. el email de prueba), con dígito verificador válido."""
    number = int(hashlib.sha1(seed.encode()).hexdigest(), 16) % 9_000_000 + 1_000_000
    return f"{number}-{compute_check_digit(number)}"
