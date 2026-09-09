"""
Pañol 360 — FastAPI Application Entry Point
Equipo: Alex (Arquitecto), Marco (Backend), Luna (UX/UI)
"""
import json
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Cookie, FastAPI, Form, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from app.core.config import settings
from app.core.branding import get_brand_css_vars, load_brand_config
from app.core.tenant import set_current_tenant
from app.api.v1.router import api_router

# ── Registro de tenants (clientes) ────────────────────────────────────────────
# El archivo tenants.json es la fuente de verdad de los alias válidos.
# La consola de administración (admin-panel) lo actualiza cuando se crea
# o suspende un cliente. Formato: { "alias": { "name": "...", "active": true } }
_TENANTS_FILE = Path("app/tenants.json")


def _load_tenants() -> dict:
    """Lee el registro de tenants desde disco. Devuelve dict vacío si no existe."""
    if _TENANTS_FILE.exists():
        try:
            return json.loads(_TENANTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # OJO: acá NO se crean las tablas (Base.metadata.create_all). El único
    # dueño del esquema es Alembic — lo corre `docker-entrypoint.sh` antes
    # de arrancar Uvicorn (o `alembic upgrade head` a mano en desarrollo
    # local sin Docker). Crearlas también acá generaba una carrera: el
    # arranque del backend armaba el esquema completo por su cuenta antes
    # de que alguien llegara a correr Alembic, y entonces Alembic fallaba
    # con "already exists" porque no tenía registrado en alembic_version
    # que esas tablas ya existían.
    yield


app = FastAPI(
    title="Pañol 360 API",
    description="Sistema de Gestión de Herramientas con Branding Dinámico",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    """
    Lee la cookie panol_tenant y registra el tenant activo en la ContextVar
    para que get_db() pueda filtrar los datos de la sesión correcta.
    Las rutas públicas (portal, terminos, privacidad, health) no tienen cookie
    y operan sin tenant — get_db() recibe None y no aplica filtro.
    """
    tenant_alias = request.cookies.get("panol_tenant")
    if tenant_alias:
        set_current_tenant(tenant_alias)
    response = await call_next(request)
    return response

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
app.include_router(api_router, prefix="/api/v1")



@app.api_route("/health", methods=["GET", "HEAD"], include_in_schema=False)
async def health_check():
    """
    Endpoint de salud para monitoreo externo (UptimeRobot, etc.).
    Responde a GET y HEAD sin autenticación — no renderiza templates
    ni accede a la BD, así que es rápido y confiable como indicador de vida.
    """
    return Response(status_code=200, media_type="text/plain", content="ok")


@app.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    """
    Bloquea el rastreo de toda la app por motores de búsqueda.
    Pañol 360 es una aplicación empresarial privada — no debe indexarse.
    """
    return FileResponse("app/static/robots.txt", media_type="text/plain")


def _tenant_env(request: Request) -> str:
    """
    Devuelve el entorno del tenant activo ('demo' o 'prod').
    Lee el campo 'env' desde tenants.json para que el admin-panel pueda
    cambiar el estado por empresa sin reiniciar el backend.
    Cae al PANOL_ENV global si el tenant no tiene el campo definido.
    """
    tenant_alias = request.cookies.get("panol_tenant")
    if tenant_alias:
        tenants = _load_tenants()
        env = tenants.get(tenant_alias, {}).get("env")
        if env in ("demo", "prod"):
            return env
    return settings.PANOL_ENV


async def _render(request: Request, template_name: str):
    """Arma el contexto común (branding) que necesita cada pantalla server-rendered."""
    brand_css = await get_brand_css_vars()
    config = load_brand_config()
    return templates.TemplateResponse(
        template_name,
        {
            "request": request,
            "brand_css": brand_css,
            "brand": config,
            "app_name": settings.APP_NAME,
            "panol_env": _tenant_env(request),  # "demo" | "prod" — por tenant o global
        },
    )


@app.get("/manifest.json")
async def manifest():
    """
    Manifest de la PWA — generado en vivo con el nombre/color de marca
    actuales, para que "instalar app" refleje la personalización de cada
    empresa en vez de un manifest.json estático genérico.
    """
    config = load_brand_config()
    name = config["company_name"]
    return JSONResponse(
        {
            "name": name,
            "short_name": name[:12],
            "description": "Sistema de Gestión de Herramientas",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#f8fafc",
            "theme_color": config["primary_color"],
            "icons": [
                {"src": "/static/img/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/static/img/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            ],
        },
        media_type="application/manifest+json",
    )


@app.get("/sw.js")
async def service_worker():
    # Servido en la raíz (no bajo /static/) a propósito: el scope de un
    # Service Worker se limita al path donde se lo sirve, y necesitamos que
    # controle todo el sitio, no solo /static/.
    return FileResponse("app/static/js/sw.js", media_type="application/javascript")


@app.get("/demo")
async def demo_redirect(request: Request):
    """
    Enlace directo al tenant de demostración pública.
    Setea la cookie panol_tenant=demo y redirige al login.
    Ideal para compartir en LinkedIn, demos con prospectos, etc.
    URL: https://panol360.app/demo
    """
    tenants = _load_tenants()
    if "demo" not in tenants or not tenants["demo"].get("active", True):
        return RedirectResponse("/portal")
    response = RedirectResponse("/login", status_code=303)
    response.set_cookie(
        key="panol_tenant",
        value="demo",
        max_age=30 * 24 * 3600,
        secure=True,
        httponly=False,
        samesite="lax",
    )
    return response


@app.get("/portal")
async def portal_page(request: Request):
    """Portal de entrada: el usuario escribe el alias de su empresa."""
    return templates.TemplateResponse("portal/index.html", {"request": request})


@app.post("/portal/verify")
async def portal_verify(request: Request, alias: str = Form(...)):
    """
    Valida el alias ingresado en el portal.
    Si es válido → setea cookie panol_tenant y redirige al login.
    Si no existe o está inactivo → muestra el portal con mensaje de error.
    """
    alias = alias.strip().lower()
    tenants = _load_tenants()

    tenant = tenants.get(alias)
    if not tenant or not tenant.get("active", True):
        return templates.TemplateResponse(
            "portal/index.html",
            {
                "request": request,
                "error": f'No encontramos la empresa "{alias}". Verificá el alias o contactá al administrador.',
                "alias": alias,
            },
            status_code=400,
        )

    # Alias válido → guardar en cookie y redirigir al login
    response = RedirectResponse("/login", status_code=303)
    response.set_cookie(
        key="panol_tenant",
        value=alias,
        max_age=30 * 24 * 3600,  # 30 días
        secure=True,
        httponly=False,   # legible por JS para mostrar nombre de empresa
        samesite="lax",
    )
    return response


@app.get("/")
async def root(request: Request, panol_tenant: str = Cookie(default=None)):
    """
    Raíz de la app. Si no hay cookie de tenant → redirige al portal.
    Si hay cookie → sirve el dashboard (el JS verifica el JWT).
    """
    tenants = _load_tenants()
    if not panol_tenant or panol_tenant not in tenants:
        return RedirectResponse("/portal")
    return await _render(request, "dashboard/index.html")


@app.get("/login")
async def login_page(request: Request, panol_tenant: str = Cookie(default=None)):
    """
    Login con branding del cliente. Si no hay cookie de tenant → portal primero.
    """
    tenants = _load_tenants()
    if not panol_tenant or panol_tenant not in tenants:
        return RedirectResponse("/portal")
    # Agregar el nombre del tenant al contexto para mostrarlo en el login
    tenant_name = tenants[panol_tenant].get("name", panol_tenant)
    brand_css = await get_brand_css_vars()
    config = load_brand_config()
    return templates.TemplateResponse(
        "auth/login.html",
        {
            "request": request,
            "brand_css": brand_css,
            "brand": config,
            "app_name": settings.APP_NAME,
            "tenant_alias": panol_tenant,
            "tenant_name": tenant_name,
            "panol_env": _tenant_env(request),
        },
    )


@app.get("/tools")
async def tools_page(request: Request):
    return await _render(request, "tools/index.html")


@app.get("/loans")
async def loans_page(request: Request):
    return await _render(request, "loans/index.html")


@app.get("/toolboxes")
async def toolboxes_page(request: Request):
    return await _render(request, "toolboxes/index.html")


@app.get("/reports")
async def reports_page(request: Request):
    return await _render(request, "reports/index.html")


@app.get("/users")
async def users_page(request: Request):
    return await _render(request, "users/index.html")


@app.get("/brand")
async def brand_settings(request: Request):
    return await _render(request, "brand/brand_settings.html")


@app.get("/lookups")
async def lookups_page(request: Request):
    return await _render(request, "lookups/index.html")


@app.get("/maintenance")
async def maintenance_page(request: Request):
    return await _render(request, "maintenance/index.html")


@app.get("/backup")
async def backup_page(request: Request):
    return await _render(request, "backup/index.html")


@app.get("/notifications")
async def notifications_page(request: Request):
    return await _render(request, "notifications/index.html")


@app.get("/terminos")
async def terms_page(request: Request):
    """Página de Términos y Condiciones — pública, no requiere cookie de tenant."""
    return templates.TemplateResponse("legal/terms.html", {"request": request})


@app.get("/privacidad")
async def privacy_page(request: Request):
    """Política de Privacidad — pública, no requiere cookie de tenant."""
    return templates.TemplateResponse("legal/privacy.html", {"request": request})


@app.get("/ayuda")
async def help_page(request: Request):
    """Manual de usuario in-app — abierto a los 3 roles, sin restricción de RBAC."""
    return await _render(request, "help/index.html")


@app.get("/ayuda/manual.pdf")
async def help_manual_pdf():
    """
    Manual de usuario en PDF. Se sirve por una ruta propia (no el link
    directo a /static/docs/...) para poder fijar el Content-Type real —
    servido tal cual por StaticFiles, algunos navegadores no lo detectaban
    bien y mostraban una descarga corrupta en vez de abrir el PDF.
    """
    return FileResponse(
        "app/static/docs/Manual_de_Usuario_Panol360.pdf",
        media_type="application/pdf",
        filename="Manual de Usuario - Pañol 360.pdf",
        content_disposition_type="inline",  # se abre en el visor de PDF del navegador, no fuerza descarga
    )


# ── Catch-all 404 ─────────────────────────────────────────────────────────────
# Debe ser la ÚLTIMA ruta registrada: FastAPI evalúa las rutas en orden y solo
# llega acá si ninguna otra coincidió.  Las peticiones a /api/... las maneja el
# api_router antes de llegar aquí, así que no las interceptamos.
@app.get("/{full_path:path}", include_in_schema=False)
async def page_not_found(request: Request, full_path: str):
    """Devuelve la página 404 personalizada para cualquier ruta desconocida."""
    brand_css = await get_brand_css_vars()
    config = load_brand_config()
    return templates.TemplateResponse(
        "errors/404.html",
        {
            "request": request,
            "brand_css": brand_css,
            "brand": config,
            "app_name": settings.APP_NAME,
        },
        status_code=404,
    )
