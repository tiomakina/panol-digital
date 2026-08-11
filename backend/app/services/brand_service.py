"""
Servicio de Branding — maneja upload de logos y extracción de paletas.
Diseñado por Luna (UX) y Marco (Backend).
"""
import os
import io
import json
import hashlib
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image
from app.core.config import settings
from app.core.branding import save_brand_config, load_brand_config, generate_palette_from_hex

UPLOAD_DIR = Path(settings.UPLOAD_DIR)
ALLOWED_MAGIC_BYTES = {
    b'\x89PNG': 'image/png',
    b'\xff\xd8\xff': 'image/jpeg',
    b'<svg': 'image/svg+xml',
    b'RIFF': 'image/webp',
}

def validate_image_magic_bytes(file_bytes: bytes) -> Tuple[bool, str]:
    """Valida el tipo real del archivo por magic bytes (no solo extensión)."""
    for magic, mime_type in ALLOWED_MAGIC_BYTES.items():
        if file_bytes[:len(magic)] == magic:
            return True, mime_type
    return False, ""

def resize_logo(image_bytes: bytes, max_width: int = 400, max_height: int = 200) -> bytes:
    """Redimensiona el logo manteniendo proporción."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((max_width, max_height), Image.LANCZOS)
        output = io.BytesIO()
        img.save(output, format=img.format or "PNG", optimize=True)
        return output.getvalue()
    except Exception:
        return image_bytes

def extract_dominant_colors(image_bytes: bytes) -> list:
    """Extrae los colores dominantes de una imagen."""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img.thumbnail((150, 150))
        colors = img.getcolors(maxcolors=10000)
        if not colors:
            return []
        # Ordenar por frecuencia y tomar los 5 más dominantes
        colors.sort(key=lambda x: x[0], reverse=True)
        dominant = []
        for count, (r, g, b) in colors[:5]:
            # Filtrar blancos y negros puros
            if not (r > 240 and g > 240 and b > 240) and not (r < 15 and g < 15 and b < 15):
                hex_color = f"#{r:02x}{g:02x}{b:02x}"
                dominant.append(hex_color)
        return dominant[:3]
    except Exception:
        return []

async def save_logo(file_bytes: bytes, filename: str) -> Optional[str]:
    """Guarda el logo y retorna la URL."""
    valid, mime_type = validate_image_magic_bytes(file_bytes)
    if not valid:
        return None
    
    # Verificar tamaño
    if len(file_bytes) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        return None
    
    # Redimensionar si es imagen bitmap (no SVG)
    if mime_type != "image/svg+xml":
        file_bytes = resize_logo(file_bytes)
    
    # Generar nombre seguro
    ext = filename.rsplit(".", 1)[-1].lower()
    safe_name = f"logo.{ext}"
    
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    logo_path = UPLOAD_DIR / safe_name
    
    with open(logo_path, "wb") as f:
        f.write(file_bytes)
    
    return f"/static/uploads/{safe_name}"

async def update_brand_from_logo(logo_bytes: bytes) -> dict:
    """Extrae colores del logo y genera paleta de branding."""
    colors = extract_dominant_colors(logo_bytes)
    if colors:
        palette = generate_palette_from_hex(colors[0].lstrip('#'))
        config = load_brand_config()
        config.update(palette)
        save_brand_config(config)
        return {"success": True, "extracted_colors": colors, "palette": palette}
    return {"success": False, "extracted_colors": [], "palette": {}}

async def update_brand_colors(color_data: dict) -> dict:
    """Actualiza los colores de branding y regenera CSS vars."""
    config = load_brand_config()
    allowed_fields = [
        "company_name", "primary_color", "secondary_color", "accent_color",
        "dark_color", "light_color", "sidebar_bg", "sidebar_text",
        "text_on_primary", "font_heading", "font_body", "border_radius"
    ]
    for field in allowed_fields:
        if field in color_data:
            config[field] = color_data[field]
    
    # Si cambió el primario, auto-calcular dark y light
    if "primary_color" in color_data:
        palette = generate_palette_from_hex(color_data["primary_color"].lstrip('#'))
        config["dark_color"] = palette["dark_color"]
        config["light_color"] = palette["light_color"]
        config["text_on_primary"] = palette["text_on_primary"]
    
    save_brand_config(config)
    return config
