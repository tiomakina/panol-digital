# Pañol 360 — Visión General del Sistema SaaS

> Documento vivo — se actualiza con cada cambio significativo.  
> Autor: Equipo virtual Pañol 360 (Alex · Luna · Marco · Sara · Diego · Kim)  
> Última actualización: 2026-09-09

---

## ¿Qué es Pañol 360?

Sistema empresarial de **gestión de herramientas** diseñado como plataforma SaaS multi-tenant. Permite a empresas del sector industrial, construcción y mantenimiento controlar:

- 🔧 **Inventario de herramientas** con estados, depreciación y QR
- 📋 **Préstamos** con vales PDF firmados y devoluciones
- 🧰 **Cajas de herramientas** asignadas a mecánicos
- 🔨 **Mantenimiento** con historial y documentos adjuntos
- 📊 **Reportes** de inventario, préstamos y auditoría
- 👥 **Usuarios** con RBAC (Jefe · Encargado · Mecánico)
- 🎨 **Branding dinámico** — logo y paleta de colores por empresa

---

## Arquitectura del sistema

```
Internet
   │
   ▼
[Nginx :80/:443]  ← reverse proxy con SSL
   │
   ├─► [FastAPI Backend :8000]  ← API + templates Jinja2
   │       │
   │       ├─► [PostgreSQL 16]  ← datos con aislamiento por tenant_id
   │       ├─► [Redis 7]        ← cache y cola de tareas
   │       └─► [Celery]         ← tareas asíncronas (notif., backups)
   │
   └─► (admin-panel y portainer NO son accesibles desde internet)

Tailscale VPN (100.x.x.x)
   │
   └─► [Admin Panel :9001]  ← consola SaaS del desarrollador

SSH Tunnel (localhost:9000)
   │
   └─► [Portainer :9000]    ← gestión visual de contenedores Docker
```

### Stack tecnológico

| Capa | Tecnología |
|---|---|
| Backend | Python 3.12 · FastAPI 0.110 · SQLAlchemy 2.0 async · Alembic |
| Frontend | HTMX 2 · Alpine.js 3 · Jinja2 · Tailwind CSS 4 |
| Base de datos | PostgreSQL 16 (multi-tenant row-level isolation) |
| Cache / Colas | Redis 7 · Celery 5 |
| Infraestructura | Docker Compose · Nginx · Oracle Cloud VPS |
| Acceso seguro | Tailscale VPN · Let's Encrypt SSL |
| Admin SaaS | FastAPI independiente (admin-panel/) · httpx · bcrypt |

---

## Modelo multi-tenant

Cada empresa (tenant) comparte el mismo servidor y base de datos. El aislamiento de datos se implementa a nivel de fila mediante la columna `tenant_id` en todas las tablas de negocio.

### Tablas con aislamiento por tenant_id
`users` · `tools` · `loans` · `toolboxes` · `toolbox_audits` · `maintenance_records` · `brand_configs` · `brands` · `categories` · `locations` · `providers` · `audit_logs`

### Flujo de aislamiento
```
Request HTTP
   │
   ▼
Middleware TenantMiddleware
   │  lee X-Tenant-ID o subdominio
   ▼
set_current_tenant(alias)  ←── contextvariable
   │
   ▼
SQLAlchemy Session (TenantSession)
   │  agrega automáticamente WHERE tenant_id = :alias
   ▼
PostgreSQL  ← cada query solo ve filas de su tenant
```

### Archivo de registro de tenants
`backend/app/tenants.json` — fuente de verdad de los alias válidos:
```json
{
  "vms-ingenieria": { "name": "VMS Ingeniería", "active": true },
  "ah": { "name": "Comercializadora AH Ltda.", "active": true }
}
```

---

## Puntos de acceso

| URL / Dirección | Quién | Para qué |
|---|---|---|
| `https://tu-dominio.cl` | Usuarios finales (empresas) | Aplicación Pañol 360 |
| `http://100.119.167.121:9001` | Desarrollador (vía Tailscale) | Consola admin SaaS |
| `localhost:9000` (SSH tunnel) | Desarrollador | Portainer Docker UI |

### Acceder a Portainer desde Windows
```bash
ssh -L 9000:localhost:9000 ubuntu@100.119.167.121
# Luego abrir: http://localhost:9000
```

---

## Consola de administración SaaS (`/tenants`)

Accesible solo vía Tailscale en `http://100.119.167.121:9001/tenants`.

### Funciones disponibles

| Acción | Cómo |
|---|---|
| Ver todos los tenants | Página principal `/tenants` |
| Ver estadísticas (usuarios, herramientas, préstamos) | Se muestran en la tabla automáticamente |
| Crear nuevo tenant | Botón **＋ Nuevo tenant** |
| Ver usuarios de un tenant | Botón **👥 Usuarios** |
| Provisionar usuario admin | Botón **👤 Nuevo** |
| Cambiar contraseña de usuario | En `/tenants/{alias}/users` → 🔑 Cambiar clave |
| Suspender / activar tenant | Botón **⏸ Suspender** / **▶ Activar** |

### Cómo agregar un nuevo cliente

1. Ir a `http://100.119.167.121:9001/tenants`
2. Clic en **＋ Nuevo tenant**
3. Completar: alias (slug único), nombre empresa, RUT admin, email, contraseña
4. El sistema:
   - Agrega la entrada a `tenants.json`
   - Crea el usuario administrador (rol Jefe) en PostgreSQL con `tenant_id = alias`
5. El cliente ya puede iniciar sesión en la aplicación

---

## Roles de usuario

| Rol | Acceso |
|---|---|
| **Jefe** | Todo: herramientas, préstamos, usuarios, reportes, administración, respaldo |
| **Encargado** | Herramientas, préstamos, cajas, mantenimiento, reportes (sin admin) |
| **Mecánico** | Solo su caja, sus propios préstamos, solicitar mantenimiento |

---

## Credenciales de prueba (tenant `vms-ingenieria`)

El login es con **RUT** (no email):

```
Jefe:       RUT 1-9      / Admin123!
Encargado:  RUT 2-7      / Admin123!
Mecánico:   RUT 3-5      / Admin123!
```

---

## Estructura del repositorio

```
panol-digital/
├── backend/                   ← FastAPI app
│   ├── app/
│   │   ├── api/v1/
│   │   │   ├── admin_api.py   ← endpoints internos para el admin-panel
│   │   │   └── router.py
│   │   ├── core/
│   │   │   ├── database.py    ← SQLAlchemy async + get_superuser_db
│   │   │   ├── tenant.py      ← middleware de aislamiento por tenant
│   │   │   └── security.py    ← JWT, bcrypt, OAuth2
│   │   ├── models/            ← ORM con TenantMixin (tenant_id en todo)
│   │   ├── templates/         ← Jinja2 HTML
│   │   └── tenants.json       ← registro de tenants activos
│   ├── alembic/versions/      ← migraciones de base de datos
│   └── docker-entrypoint.sh   ← corre `alembic upgrade head` al arrancar
│
├── admin-panel/               ← consola SaaS del desarrollador
│   ├── main.py                ← FastAPI app + rutas de tenants
│   └── templates/
│       ├── tenants.html       ← lista de tenants con estadísticas
│       └── tenant_users.html  ← usuarios de un tenant + cambio de clave
│
├── docker-compose.yml         ← orquestación completa
├── nginx.conf                 ← reverse proxy
├── CLAUDE.md                  ← instrucciones para el asistente AI
├── SAAS_OVERVIEW.md           ← este archivo
└── SESSION.md                 ← contexto de sesión activo
```

---

## Seguridad

- **Admin Panel**: protegido por usuario + contraseña bcrypt + solo accesible vía Tailscale VPN (IP 100.119.167.121). El puerto 9001 está cerrado en Oracle Cloud Security List.
- **API interna admin**: header `X-Admin-Token` con secreto compartido (`ADMIN_API_SECRET`). Nunca expuesto a internet.
- **JWT**: tokens de sesión con expiración para los usuarios finales.
- **Row-level isolation**: cada query filtra automáticamente por `tenant_id`.
- **RBAC**: cada endpoint verifica el rol del usuario además del tenant.
- **Uploads**: validación de tipo de archivo por magic bytes (no solo extensión).
- **Contraseñas**: bcrypt con salt, nunca en texto plano.

---

## Historial de versiones

### v0.1 — Sistema base mono-tenant
- Módulos: Herramientas, Préstamos, Cajas, Mantenimiento, Reportes, Usuarios
- RBAC con 3 roles (Jefe, Encargado, Mecánico)
- Branding dinámico por empresa (logo + paleta de colores)
- PDF de vales y documentos de mantenimiento
- Backup y restauración desde la UI
- Tour guiado in-app + Módulo de Ayuda + Manual de Usuario (Word)
- QR por herramienta

### v0.2 — Infraestructura SaaS (multi-tenant) — 2026-09-08
- Migración Alembic `a1b2c3d4e5f6`: columna `tenant_id` en todas las tablas
- Middleware de aislamiento: cada sesión filtra automáticamente por tenant
- `tenants.json`: registro de empresas activas
- `scripts/provision_tenant.sh`: script de provisionamiento desde terminal
- Cabeceras de seguridad Nginx (X-Frame-Options, CSP, HSTS)
- Badge "DEMO" en entornos de demostración (`PANOL_ENV=demo`)

### v0.3 — Consola de administración SaaS — 2026-09-09
- Admin Panel en puerto 9001 (acceso solo vía Tailscale)
- API interna protegida con `X-Admin-Token` (`/api/v1/admin/*`)
- Dashboard de tenants: estadísticas en tiempo real (usuarios, herramientas, préstamos)
- Crear tenant + provisionar usuario admin desde UI
- Ver usuarios de cada tenant
- Cambiar contraseña de cualquier usuario desde la consola
- Suspender / activar tenants
- Red Docker interna (`panol-net`) para comunicación admin-panel ↔ backend
- Migración idempotente (IF NOT EXISTS) — reentrante ante fallos parciales

---

## Próximos pasos sugeridos

- [ ] Subdominio por tenant (`ah.panol360.cl`, `vms.panol360.cl`)
- [ ] Facturación y control de plan (herramientas máximas, usuarios máximos)
- [ ] Onboarding automático: email de bienvenida al provisionar tenant
- [ ] Logs de actividad por tenant desde el admin panel
- [ ] Dashboard de métricas SaaS: MRR, churn, uso por tenant
- [ ] Backup automatizado por tenant (scheduler Celery)
- [ ] 2FA para el admin panel

---

*Documento generado y mantenido por el equipo virtual de desarrollo Pañol 360.*  
*Actualizar este archivo con cada feature, fix o cambio arquitectónico significativo.*
