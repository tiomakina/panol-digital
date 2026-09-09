"""
Motor de Branding Dinámico — componente central del sistema.
Gestiona logos, paletas de colores y CSS custom properties por empresa.

Multi-tenant: cada empresa tiene su propia carpeta dentro de UPLOAD_DIR.
  Ruta por tenant: {UPLOAD_DIR}/{tenant_id}/brand_config.json
  Ruta global (fallback sin tenant): {UPLOAD_DIR}/brand_config.json
"""
import json
from pathlib import Path
from typing import Optional
from app.core.config import settings


UPLOAD_DIR = Path(settings.UPLOAD_DIR)

DEFAULT_BRAND = {
    "company_name": settings.COMPANY_NAME,
    "primary_color": settings.COMPANY_PRIMARY_COLOR,
    "secondary_color": settings.COMPANY_SECONDARY_COLOR,
    "accent_color": settings.COMPANY_ACCENT_COLOR,
    "dark_color": "#1e1b4b",
    "light_color": "#ede9fe",
    "sidebar_bg": "#0f172a",
    "sidebar_text": "#e2e8f0",
    "logo_url": "/static/img/logo_default.svg",
    "font_heading": "Inter",
    "font_body": "Inter",
    "border_radius": "8px",
    "text_on_primary": "#ffffff",
}


def _get_brand_config_file(tenant_id: Optional[str] = None) -> Path:
    """
    Devuelve la ruta del brand_config.json para el tenant dado.
    Si no se pasa tenant_id, lo lee del contexto activo de la petición.
    """
    if tenant_id is None:
        # Import diferido para evitar ciclo con tenant.py al cargar el módulo
        from app.core.tenant import get_current_tenant
        tenant_id = get_current_tenant()

    if tenant_id:
        # Ruta per-tenant: uploads/{tenant_id}/brand_config.json
        return UPLOAD_DIR / tenant_id / "brand_config.json"
    # Fallback para peticiones sin tenant (portal, legales, etc.)
    return UPLOAD_DIR / "brand_config.json"


def load_brand_config(tenant_id: Optional[str] = None) -> dict:
    """
    Carga la configuración de branding del tenant activo desde disco.
    Si no existe un archivo para ese tenant, devuelve los valores por defecto.
    """
    cfg_file = _get_brand_config_file(tenant_id)
    if cfg_file.exists():
        try:
            with open(cfg_file) as f:
                return {**DEFAULT_BRAND, **json.load(f)}
        except Exception:
            pass
    return DEFAULT_BRAND.copy()


def save_brand_config(config: dict, tenant_id: Optional[str] = None) -> None:
    """
    Guarda la configuración de branding del tenant activo en disco.
    Crea el directorio del tenant si no existe.
    """
    cfg_file = _get_brand_config_file(tenant_id)
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg_file, "w") as f:
        json.dump(config, f, indent=2)


def init_brand_for_tenant(tenant_id: str, company_name: str) -> None:
    """
    Inicializa el brand_config.json para un nuevo tenant con su nombre de empresa.
    Se llama al provisionar un nuevo cliente para que no vea "Mi Empresa" por defecto.
    No sobreescribe si ya existe configuración propia del tenant.
    """
    cfg_file = _get_brand_config_file(tenant_id)
    if cfg_file.exists():
        return  # Ya tiene configuración propia, no tocar
    brand = DEFAULT_BRAND.copy()
    brand["company_name"] = company_name
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg_file, "w") as f:
        json.dump(brand, f, indent=2)


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
