# 🔧 Pañol v2.0 — Sistema de Gestión de Herramientas

## Visión del proyecto
Sistema empresarial de gestión de herramientas con **branding dinámico por empresa**. 
Cada organización puede subir su logo y personalizar la paleta de colores completa.
Diseñado para usuarios sin conocimientos de informática. Instalación en 1 clic.

## Equipo virtual de desarrollo
- **Alex** — Arquitecto: FastAPI, PostgreSQL 16, microservicios
- **Luna** — UX/UI Lead: Design system, dark mode, mobile-first, WCAG 2.2
- **Marco** — Backend Sr.: Python async, SQLAlchemy 2.0, JWT
- **Sara** — Frontend Sr.: HTMX 2, Alpine.js 3, PWA, Chart.js 4
- **Diego** — Security: RBAC granular, auditoría forense, 2FA
- **Kim** — DevOps: Docker, PyInstaller GUI installer, GitHub Actions

## Stack tecnológico

### Backend
- Python 3.12 + FastAPI 0.110
- PostgreSQL 16 + SQLAlchemy 2.0 (async) + Alembic
- Redis 7 + Celery 5
- JWT (python-jose) + OAuth2 + bcrypt

### Frontend
- HTMX 2 + Alpine.js 3 (NO React/Vue/Angular)
- Tailwind CSS 4 con CSS custom properties para theming dinámico
- Chart.js 4 + ApexCharts para gráficos
- PWA con Service Worker (offline support)
- Jinja2 templates (server-side rendering)

### Infraestructura
- Docker Compose (PostgreSQL + Redis + FastAPI + Nginx)
- Nginx como reverse proxy con SSL automático
- PyInstaller para instalador GUI (tkinter)
- Portainer para gestión visual de contenedores

### Sistema de Branding Dinámico (CRÍTICO)
- CSS Custom Properties (variables) para theming en tiempo real
- Subida de logo vía drag & drop (PNG/SVG/JPG, max 2MB)
- Paleta de colores con color picker HSL
- Generación automática de paleta desde logo (color-thief)
- Persistencia en PostgreSQL + archivos estáticos
- Aplicación instantánea sin reload de página

## Estructura del proyecto

```
panol-v2/
├── CLAUDE.md                    ← Este archivo
├── docker-compose.yml           ← Orquestación completa
├── docker-compose.dev.yml       ← Solo para desarrollo
├── .env.example                 ← Variables de entorno
├── Makefile                     ← Comandos útiles
│
├── backend/
│   ├── app/
│   │   ├── main.py              ← FastAPI app + lifespan
│   │   ├── core/
│   │   │   ├── config.py        ← Settings con pydantic-settings
│   │   │   ├── database.py      ← Async SQLAlchemy engine
│   │   │   ├── security.py      ← JWT, bcrypt, OAuth2
│   │   │   └── branding.py      ← Motor de branding dinámico
│   │   ├── models/              ← SQLAlchemy ORM models
│   │   │   ├── user.py
│   │   │   ├── tool.py
│   │   │   ├── loan.py
│   │   │   ├── toolbox.py
│   │   │   ├── brand.py         ← BrandConfig model
│   │   │   └── audit.py
│   │   ├── schemas/             ← Pydantic v2 schemas
│   │   ├── api/v1/
│   │   │   ├── router.py
│   │   │   ├── auth.py
│   │   │   ├── tools.py
│   │   │   ├── loans.py
│   │   │   ├── toolboxes.py
│   │   │   ├── reports.py
│   │   │   ├── users.py
│   │   │   ├── brand.py         ← API de branding
│   │   │   └── dashboard.py
│   │   ├── services/            ← Business logic
│   │   │   ├── tool_service.py
│   │   │   ├── loan_service.py
│   │   │   ├── depreciation.py  ← 3 métodos de depreciación
│   │   │   ├── pdf_service.py   ← Vales PDF con firma
│   │   │   ├── qr_service.py    ← Generador de QR
│   │   │   └── brand_service.py ← Extracción paleta del logo
│   │   ├── templates/           ← Jinja2 HTML
│   │   │   ├── base.html        ← Layout base con theming
│   │   │   ├── auth/
│   │   │   ├── dashboard/
│   │   │   ├── tools/
│   │   │   ├── loans/
│   │   │   ├── toolboxes/
│   │   │   ├── reports/
│   │   │   ├── users/
│   │   │   ├── brand/           ← Pantalla de branding
│   │   │   └── components/      ← Partials HTMX
│   │   └── static/
│   │       ├── css/
│   │       │   ├── app.css      ← Tailwind + CSS vars theming
│   │       │   └── brand.css    ← Variables dinámicas
│   │       ├── js/
│   │       │   ├── app.js       ← Alpine.js stores
│   │       │   ├── charts.js    ← Chart.js configuración
│   │       │   ├── qr-scanner.js ← QR via cámara
│   │       │   └── brand.js     ← Color picker + logo upload
│   │       └── uploads/         ← Logos empresariales
│   ├── alembic/
│   ├── tests/
│   └── requirements.txt
│
├── scripts/
│   ├── instalador_gui.py        ← Instalador PyInstaller
│   ├── backup.sh
│   ├── restore.sh
│   └── build_installer.sh       ← Compila el .exe/.dmg
│
└── docs/
    ├── README.md
    ├── INSTALACION.md
    └── API.md
```

## Reglas de desarrollo

### Código
- Siempre async/await en FastAPI (no funciones síncronas en endpoints)
- Type hints en todo el código Python
- Pydantic v2 para todos los schemas
- Comentarios en español para el equipo
- Manejo de errores con HTTPException apropiado

### Frontend
- HTMX para toda la interactividad (no escribir fetch/axios manualmente)
- Alpine.js solo para estado de UI local (modales, dropdowns)
- CSS variables para TODOS los colores (permite theming dinámico)
- Mobile first siempre (320px mínimo)
- Dark mode via `prefers-color-scheme` + toggle manual

### Branding dinámico
- Las variables CSS se generan server-side y se inyectan en `<style>` en base.html
- El logo se sirve desde /static/uploads/{company_id}/logo.{ext}
- La paleta se guarda en tabla `brand_configs` en PostgreSQL
- Cada cambio de branding dispara un evento HTMX para actualizar la UI

### Seguridad
- NUNCA exponer claves en código — siempre desde .env
- Validar tipos de archivo en uploads (magic bytes, no solo extensión)
- Rate limiting en todos los endpoints de auth
- CSRF token en todos los formularios

## Comandos frecuentes

```bash
# Desarrollo
make dev          # Levanta backend + frontend en modo watch
make migrate      # Crea y aplica migraciones
make seed         # Carga datos de prueba
make test         # Corre pytest

# Docker
make up           # docker-compose up -d
make down         # docker-compose down
make logs         # Ver logs de todos los servicios
make shell        # Shell en el contenedor backend

# Instalador
make build-installer  # Genera .exe + .dmg + .run con PyInstaller
```

## Decisiones de arquitectura

### Por qué HTMX en vez de React/Vue
- El usuario final no necesita SPA compleja
- Menos JavaScript = menos bugs = más fácil de mantener
- Server-side rendering = mejor SEO y primera carga
- Un solo lenguaje (Python) para todo el backend

### Por qué FastAPI en vez de Django
- 3x más rápido que Django REST
- Async nativo = mejor para WebSockets (KPIs en tiempo real)
- OpenAPI/Swagger generado automáticamente
- Type hints obligatorios = menos errores

### Por qué CSS custom properties para theming
- Cambia toda la paleta con 5 variables en tiempo real
- No requiere rebuild de Tailwind
- Funciona en todos los navegadores modernos
- El usuario ve el cambio de color instantáneamente

## Credenciales de prueba
```
Admin (Jefe):       admin@panol.com / Admin123!
Encargado:          encargado@panol.com / Admin123!
Mecánico:           mecanico@panol.com / Admin123!
```
