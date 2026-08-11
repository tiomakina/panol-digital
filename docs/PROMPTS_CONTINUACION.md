# Prompts de Continuación — Pañol v2.0

## Prompt para continuar en Claude Code

```
Continúa el desarrollo del proyecto Pañol v2.0 en /home/claude/panol-v2/.
Lee el archivo CLAUDE.md primero para entender el contexto completo.

EQUIPO VIRTUAL:
- Alex (Arquitecto), Luna (UX/UI), Marco (Backend), Sara (Frontend), Diego (Security), Kim (DevOps)

STACK: FastAPI + PostgreSQL + HTMX 2 + Alpine.js + Tailwind + Docker + PyInstaller GUI

LO QUE ESTÁ HECHO:
✅ CLAUDE.md — inteligencia del proyecto completa
✅ backend/app/main.py — FastAPI entry point
✅ backend/app/core/ — config, database, security, branding engine
✅ backend/app/models/ — user, tool, loan, brand (SQLAlchemy 2.0)
✅ backend/app/services/brand_service.py — upload logo + extracción colores
✅ backend/app/api/v1/brand.py — API de branding
✅ backend/app/templates/base.html — layout con theming dinámico
✅ backend/app/templates/brand/brand_settings.html — UI personalización completa
✅ backend/app/templates/dashboard/index.html — dashboard con KPIs
✅ docker-compose.yml — PostgreSQL + Redis + FastAPI + Nginx + Portainer
✅ scripts/instalador_gui.py — instalador PyInstaller con tkinter
✅ requirements.txt, Makefile, .env.example

NECESITO QUE DESARROLLES:
[ESPECIFICAR AQUÍ — ejemplo:]
1. backend/app/api/v1/auth.py — Login/logout con JWT, refresh tokens, rate limiting
2. backend/app/api/v1/tools.py — CRUD completo herramientas con fotos y QR
3. backend/app/api/v1/loans.py — Préstamos + generación de vales PDF
4. backend/app/templates/auth/login.html — Pantalla de login con el branding dinámico
5. backend/app/services/pdf_service.py — Generación de vales PDF con ReportLab
6. backend/app/services/qr_service.py — Generación y lectura de códigos QR
```

## Prompt para continuar en otra IA (GPT-4, Gemini, etc.)

```
Contexto: Sistema Pañol v2.0 — Gestión de herramientas empresarial con branding dinámico.

ARQUITECTURA IMPLEMENTADA:
- Backend: FastAPI 0.110 + Python 3.12 + PostgreSQL 16 async + Redis + Celery
- Frontend: HTMX 2 + Alpine.js 3 + Tailwind CSS + Jinja2 templates
- Branding: CSS Custom Properties dinámicas, logo upload + extracción de paleta
- Infraestructura: Docker Compose + Nginx + Portainer + PyInstaller GUI installer

MÓDULOS COMPLETADOS:
✅ Sistema de branding dinámico (logo + paleta de colores personalizable por empresa)
✅ Motor de CSS custom properties para theming en tiempo real
✅ Extracción automática de colores del logo con Pillow
✅ Instalador GUI con tkinter (sin terminal, 1 clic para usuarios no técnicos)
✅ Base de datos con modelos para User, Tool, Loan, BrandConfig

NECESITO DESARROLLAR:
[ESPECIFICAR MÓDULO]

Stack exacto: FastAPI async, SQLAlchemy 2.0 mapped_column, Pydantic v2.
Templates: Jinja2 + HTMX 2 (hx-get, hx-post, hx-swap, hx-target).
Todos los colores en CSS usan var(--brand-primary) etc., nunca hex hardcodeado.
Comentarios del código en español.
```
