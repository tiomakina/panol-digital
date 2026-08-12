"""
Pañol v2.0 — FastAPI Application Entry Point
Equipo: Alex (Arquitecto), Marco (Backend), Luna (UX/UI)
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from app.core.config import settings
from app.core.database import create_tables
from app.core.branding import get_brand_css_vars, load_brand_config
from app.api.v1.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(
    title="Pañol v2.0 API",
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

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
app.include_router(api_router, prefix="/api/v1")


async def _render(request: Request, template_name: str):
    """Arma el contexto común (branding) que necesita cada pantalla server-rendered."""
    brand_css = await get_brand_css_vars()
    config = load_brand_config()
    return templates.TemplateResponse(
        template_name,
        {"request": request, "brand_css": brand_css, "brand": config, "app_name": settings.APP_NAME},
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


@app.get("/")
async def root(request: Request):
    return await _render(request, "dashboard/index.html")


@app.get("/login")
async def login_page(request: Request):
    return await _render(request, "auth/login.html")


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
