"""
API de Branding — upload de logo y personalización de paleta.
Endpoint: /api/v1/brand/
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from app.core.security import require_role
from app.core.branding import load_brand_config, get_brand_css_vars
from app.services.brand_service import save_logo, update_brand_from_logo, update_brand_colors

router = APIRouter(prefix="/brand", tags=["Branding"])


class ColorUpdate(BaseModel):
    company_name: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    accent_color: str | None = None
    sidebar_bg: str | None = None
    font_heading: str | None = None
    font_body: str | None = None
    border_radius: str | None = None


@router.get("/config")
async def get_brand_config(user=Depends(require_role("encargado"))):
    """Obtiene la configuración de branding actual."""
    return load_brand_config()


@router.post("/logo")
async def upload_logo(
    file: UploadFile = File(...),
    extract_palette: bool = True,
    user=Depends(require_role("jefe"))
):
    """
    Sube el logo de la empresa.
    Si extract_palette=True, extrae automáticamente los colores del logo.
    """
    if not file.content_type or "image" not in file.content_type:
        raise HTTPException(status_code=400, detail="Solo se permiten imágenes (PNG, JPG, SVG, WebP)")
    
    file_bytes = await file.read()
    
    # Guardar logo
    logo_url = await save_logo(file_bytes, file.filename or "logo.png")
    if not logo_url:
        raise HTTPException(status_code=400, detail="Archivo inválido o demasiado grande (máx. 2MB)")
    
    result = {"logo_url": logo_url, "palette": {}}
    
    # Extraer paleta automáticamente si se solicita
    if extract_palette and file.content_type != "image/svg+xml":
        palette_result = await update_brand_from_logo(file_bytes)
        result["palette"] = palette_result.get("palette", {})
        result["extracted_colors"] = palette_result.get("extracted_colors", [])
    
    # Actualizar URL del logo en config
    from app.core.branding import load_brand_config, save_brand_config
    config = load_brand_config()
    config["logo_url"] = logo_url
    save_brand_config(config)
    
    return result


@router.put("/colors")
async def update_colors(
    colors: ColorUpdate,
    user=Depends(require_role("jefe"))
):
    """Actualiza la paleta de colores de branding."""
    updated_config = await update_brand_colors(colors.model_dump(exclude_none=True))
    return {"success": True, "config": updated_config}


@router.get("/css")
async def get_css_variables():
    """
    Devuelve las CSS custom properties actuales.
    Se usa para inyectar en el <head> de cada página.
    """
    css = await get_brand_css_vars()
    return {"css": css}


@router.post("/reset")
async def reset_brand(user=Depends(require_role("jefe"))):
    """Resetea el branding a los valores por defecto."""
    from app.core.branding import DEFAULT_BRAND, save_brand_config
    save_brand_config(DEFAULT_BRAND.copy())
    return {"success": True, "message": "Branding restaurado a valores predeterminados"}
