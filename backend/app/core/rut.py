"""
Validación y formateo de RUT chileno (módulo 11) — se usa como identificador
único de cada usuario (reemplaza al email como credencial de login: el
email puede cambiar con el tiempo, el RUT no).
"""
import re


def clean_rut(rut: str) -> str:
    """Saca puntos, espacios y guiones, deja mayúscula el dígito verificador K."""
    return re.sub(r"[.\s-]", "", rut or "").upper()


def compute_check_digit(number: int) -> str:
    """
    Dígito verificador módulo 11 — multiplica cada dígito (de derecha a
    izquierda) por la secuencia 2,3,4,5,6,7,2,3,4..., suma, y el resultado
    es 11 menos el resto de esa suma sobre 11 (11→'0', 10→'K').
    """
    total = 0
    factor = 2
    for digit in reversed(str(number)):
        total += int(digit) * factor
        factor = 2 if factor == 7 else factor + 1
    remainder = 11 - (total % 11)
    if remainder == 11:
        return "0"
    if remainder == 10:
        return "K"
    return str(remainder)


def is_valid_rut(rut: str) -> bool:
    """True si el string es un RUT chileno válido (formato + dígito verificador)."""
    cleaned = clean_rut(rut)
    if not re.fullmatch(r"\d{1,8}[0-9K]", cleaned):
        return False
    number, check_digit = cleaned[:-1], cleaned[-1]
    return compute_check_digit(int(number)) == check_digit


def format_rut(rut: str) -> str:
    """
    Formato canónico de guardado: "NNNNNNNN-D", sin puntos. No es el formato
    "bonito" con puntos de miles (ese es cosa de la UI) — este es el que se
    compara para unicidad, así que tiene que ser siempre el mismo sin
    importar cómo lo haya tipeado quien lo carga (con o sin puntos).
    """
    cleaned = clean_rut(rut)
    return f"{cleaned[:-1]}-{cleaned[-1]}"
