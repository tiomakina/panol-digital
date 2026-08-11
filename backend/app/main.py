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
from app.core.config import settings
from app.core.database import create_tables
from app.core.branding import get_brand_css_vars
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


@app.get("/")
async def root(request: Request):
    brand_css = await get_brand_css_vars()
    return templates.TemplateResponse(
        "dashboard/index.html",
        {"request": request, "brand_css": brand_css, "app_name": settings.APP_NAME}
    )

@app.get("/brand")
async def brand_settings(request: Request):
    brand_css = await get_brand_css_vars()
    from app.core.branding import load_brand_config
    config = load_brand_config()
    return templates.TemplateResponse(
        "brand/brand_settings.html",
        {"request": request, "brand_css": brand_css, "brand": config}
    )

@app.get("/login")
async def login_page(request: Request):
    brand_css = await get_brand_css_vars()
    from app.core.branding import load_brand_config
    config = load_brand_config()
    return templates.TemplateResponse(
        "auth/login.html",
        {"request": request, "brand_css": brand_css, "brand": config}
    )
