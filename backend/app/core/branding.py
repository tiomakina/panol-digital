"""
Motor de Branding Dinámico — componente central del sistema.
Gestiona logos, paletas de colores y CSS custom properties por empresa.
"""
import os
import json
from pathlib import Path
from typing import Optional
from app.core.config import settings


# Ruta al archivo de configuración de branding
BRAND_CONFIG_FILE = Path(settings.UPLOAD_DIR) / "brand_config.json"

DEFAULT_BRAND = {
    "company_name": settings.COMPANY_NAME,
    "primary_color": settings.COMPANY_PRIMARY_COLOR,
    "secondary_color": settings.COMPANY_SECONDARY_COLOR,
    "accent_color": settings.COMPANY_ACCENT_COLOR,
    "dark_color": "#1e1b4b",
    "light_color": "#ede9fe",
    "sidebar_bg": "#0f172a",
    "sidebar_text": "#e2e8f0",
    "logo_url": "/static/uploads/logo_default.svg",
    "font_heading": "Inter",
    "font_body": "Inter",
    "border_radius": "8px",
    "text_on_primary": "#ffffff",
}


def load_brand_config() -> dict:
    """Carga la configuración de branding desde disco."""
    if BRAND_CONFIG_FILE.exists():
        with open(BRAND_CONFIG_FILE) as f:
            return {**DEFAULT_BRAND, **json.load(f)}
    return DEFAULT_BRAND.copy()


def save_brand_config(config: dict) -> None:
    """Guarda la configuración de branding en disco."""
    BRAND_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(BRAND_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


async def get_brand_css_vars() -> str:
    """
    Genera el bloque CSS con las variables de branding.
    Se inyecta en el <head> de cada página.
    """
    config = load_brand_config()
    
    # Calcular variantes de color automáticamente
    primary = config["primary_color"]
    
    css = f"""
    :root {{
        --brand-primary: {config['primary_color']};
        --brand-secondary: {config['secondary_color']};
        --brand-accent: {config['accent_color']};
        --brand-dark: {config['dark_color']};
        --brand-light: {config['light_color']};
        --brand-sidebar-bg: {config['sidebar_bg']};
        --brand-sidebar-text: {config['sidebar_text']};
        --brand-text-on-primary: {config['text_on_primary']};
        --brand-font-heading: '{config['font_heading']}', 'Inter', sans-serif;
        --brand-font-body: '{config['font_body']}', 'Inter', sans-serif;
        --brand-radius: {config['border_radius']};
        --brand-company-name: '{config['company_name']}';
    }}
    """
    return css


def generate_palette_from_hex(hex_color: str) -> dict:
    """
    Genera una paleta completa desde un color primario.
    Calcula secundario, acento, dark y light automáticamente.
    """
    # Convertir hex a RGB
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    
    # Calcular versión oscura (30% más oscuro)
    dark_r = max(0, int(r * 0.4))
    dark_g = max(0, int(g * 0.4))
    dark_b = max(0, int(b * 0.4))
    dark_hex = f"#{dark_r:02x}{dark_g:02x}{dark_b:02x}"
    
    # Calcular versión clara (80% más claro)
    light_r = min(255, int(r + (255 - r) * 0.85))
    light_g = min(255, int(g + (255 - g) * 0.85))
    light_b = min(255, int(b + (255 - b) * 0.85))
    light_hex = f"#{light_r:02x}{light_g:02x}{light_b:02x}"
    
    # Color complementario (rotar 30 grados en HSL) — simplificado
    complementary = f"#{b:02x}{r:02x}{g:02x}"
    
    # Determinar si el texto sobre primario debe ser blanco o negro
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    text_on_primary = "#ffffff" if luminance < 128 else "#1a1a1a"
    
    return {
        "primary_color": f"#{hex_color}",
        "dark_color": dark_hex,
        "light_color": light_hex,
        "text_on_primary": text_on_primary,
        "secondary_color": "#06b6d4",  # Se puede personalizar
        "accent_color": "#f59e0b",     # Se puede personalizar
    }
