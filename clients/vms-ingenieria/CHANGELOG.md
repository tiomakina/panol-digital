# Bitácora de Cambios — VMS Ingeniería

> Registro cronológico de todos los cambios aplicados a este cliente.
> Agregar entradas con: `bash scripts/admin.sh log vms-ingenieria "descripción"`

---

## 2026-09-03 (noche)

### Alerta de stock mínimo de herramientas
- ✅ Nuevo campo `min_stock` (nullable) en modelo `Tool` + migración Alembic `b4e7a2c91d38`
- ✅ Concepto: stock se agrupa por `product_code` (si existe) o por `nombre+marca` — permite tener N unidades del mismo tipo
- ✅ `list_tools()` calcula `available_count` y `low_stock` desde los datos ya cargados (sin queries extra)
- ✅ Badge **⚠ Stock bajo** en la tabla de herramientas (visible solo para Encargado/Jefe)
- ✅ Campo "Stock mínimo disponible" en formulario crear/editar herramienta
- ✅ `create_loan()`: post-commit, si el stock disponible cae bajo el mínimo → avisa por email a todos los Encargados/Jefes activos vía `notify_low_stock()`
- 📝 Requiere SMTP configurado en `.env` para el aviso por email

---

## 2026-09-03 (tarde)

### Exportación de reportes a PDF
- ✅ Nuevo servicio `report_pdf_service.py`: genera PDFs A4 horizontal para Inventario, Préstamos y Mantenimiento usando `reportlab` con branding dinámico (color primario y nombre de empresa en la cabecera)
- ✅ Tres endpoints nuevos en `/api/v1/reports`: `GET /inventory.pdf`, `/loans.pdf`, `/maintenance.pdf` — mismos filtros que sus homólogos JSON/CSV
- ✅ Botón "⬇ PDF" en las tres pestañas del módulo Reportes (Inventario, Préstamos, Mantenimiento)
- ✅ Funciones JS `downloadInventoryPdf()`, `downloadLoansPdf()`, `downloadMaintenancePdf()` en el componente Alpine `reportsPage()`

### Recordatorio pre-vencimiento de préstamos (Celery)
- ✅ Columna `reminder_sent` en modelo `Loan` + migración Alembic `3a1f72d8e9c4`
- ✅ Tarea Celery `send_loan_reminders`: busca préstamos activos que vencen mañana y envía aviso por email y/o WhatsApp al responsable; marca `reminder_sent=True` para no re-enviar
- ✅ Registrada en beat schedule: corre a las 08:00 UTC (11:00 Chile hora verano)
- 📝 **Requiere** configurar SMTP en `.env` del servidor para activar el envío real (código ya listo)

---

## 2026-09-03

### Panel de administración SaaS (Tailscale)
- ✅ Nuevo servicio `admin-panel` en puerto 9001, accesible solo vía Tailscale VPN
- ✅ Autenticación propia con usuario + contraseña bcrypt (independiente del backend)
- ✅ Lectura de directorio `clients/` con stats de clientes (total / activos / demo / suspendidos)
- ✅ Bitácora por cliente con categorías (deploy / backup / config / soporte / incidencia)
- ✅ Pestaña de comandos: SSH, deploy, logs, backup, shell — copyable al portapapeles
- ✅ Seguridad: Oracle Cloud Security List bloquea 9001 desde internet; solo red Tailscale 100.x.x.x accede
- ✅ Guía completa documentada en `docs/TAILSCALE.md`

### Corrección: sidebar mobile no visible
- 🔧 **Causa raíz**: Service Worker `panol-shell-v1` cachéaba `alpine.min.js` indefinidamente; en Android mobile el caché estaba stale y Alpine.js no inicializaba
- 🔧 **Fix 1**: `sw.js` — nombre de caché bumpeado `v1 → v3` para forzar descarga fresca de todos los archivos vendor (Alpine, HTMX, Chart.js)
- 🔧 **Fix 2**: `base.html` — fallback vanilla JS que activa a 600ms; si Alpine no inicializó (`body._x_dataStack` ausente), agrega click handler directo sobre `.sidebar` para toggle de clase `.open` en mobile y `.collapsed` en desktop
- ✅ Verificado funcionando en Android Chrome (modo mobile) después de borrar datos del sitio

---

## 2026-09-02

### Deployment inicial
- ✅ Primer deploy en Oracle Cloud Free Tier (Ubuntu 24.04.4 LTS)
- ✅ Dominio configurado: demopanol.valentinmorales.cl
- ✅ SSL Let's Encrypt activado
- ✅ Stack Docker completo: nginx, backend, PostgreSQL 16, Redis 7, Celery, Portainer
- ✅ Datos de ejemplo cargados (seed_data.py)
- ✅ Branding VMS Ingeniería: logo hexagonal azul, paleta #1d4ed8 / #f97316
- ✅ 59 CVEs de dependencias Python resueltos
- ✅ Portainer restringido a localhost (túnel SSH)
- ✅ PostgreSQL y Redis no expuestos a internet

### Seguridad y producción
- ✅ SECRET_KEY y JWT_SECRET_KEY configurados en .env del servidor
- ✅ Certbot auto-renewal: cron diario 03:00
- ✅ Backup automático: cron diario 02:00 → /home/ubuntu/panol-digital/backups/
- ✅ Limpieza de backups >7 días: cron diario 04:00
- ✅ Íconos PWA: icon-192.png + icon-512.png con branding VMS
- ✅ Endpoint /health para monitoreo externo (GET + HEAD)
- ✅ UptimeRobot configurado: monitor HTTPS cada 5 min, alertas email + push

### Correcciones aplicadas
- 🔧 docker-compose.yml: eliminado `version: '3.9'` obsoleto
- 🔧 backup.sh / restore.sh: fix de parseo seguro de .env con caracteres especiales
- 🔧 404 personalizado: catch-all route en FastAPI (página de error con branding)
- 🔧 scripts/setup_production.sh: script de setup inicial de producción

---

## 2026-09-01

### Infraestructura y seguridad pre-producción
- ✅ SSL/TLS con Let's Encrypt para `demopanol.valentinmorales.cl` (certbot webroot)
- ✅ Nginx: HTTP→HTTPS redirect, TLS 1.2/1.3, HSTS, headers de seguridad completos
- ✅ Página 404 personalizada con branding dinámico (catch-all route en FastAPI)
- ✅ `robots.txt` para bloquear indexación de la app
- ✅ PostgreSQL y Redis sin puertos expuestos a internet
- ✅ Portainer sin setup token (`--no-setup-token`); acceso solo por túnel SSH
- ✅ 59 CVEs resueltos en dependencias Python (cryptography, certifi, pillow, etc.)
- ✅ Fix Nginx: eliminado bloque `types{}` en `/static/` que servía .js como octet-stream

### Branding inicial VMS Ingeniería
- ✅ Paleta azul #1d4ed8 / naranja #f97316 aplicada al sistema de branding dinámico
- ✅ Logo hexagonal corporativo subido y configurado en Personalización

---

## 2026-08-18

### Sistema de ayuda y documentación in-app
- ✅ Motor de tour guiado vanilla JS (`tour.js`): overlay con spotlight, popover por pasos, sin librerías externas
- ✅ Tour activado en cada módulo principal (botón "¿Cómo uso esto?" visible en topbar)
- ✅ Sección `/ayuda` in-app: artículos por módulo para los 3 roles (Jefe / Encargado / Mecánico)
- ✅ Manual de usuario completo en PDF con capturas reales de la app
- ✅ Descarga del manual directamente desde la app

### Correcciones
- 🔧 Auditoría: columna "Identidad" mostraba "user #1" en vez del nombre real → corregido
- 🔧 Manual: descarga fallaba en producción → ruta corregida; solo PDF (Word eliminado)
- 🔧 6 vulnerabilidades de seguridad críticas/altas adicionales resueltas
- 🔧 Healthcheck PostgreSQL: especifica `-d panol_db` explícitamente para evitar falsos negativos

---

## 2026-08-17

### Control de acceso por rol (RBAC completo)
- ✅ Matriz de permisos: Jefe > Encargado > Mecánico implementada en todos los módulos
- ✅ Dashboard: valor del inventario oculto para Mecánico
- ✅ Herramientas: exportar CSV y editar bloqueado para Mecánico
- ✅ Préstamos: Mecánico solo ve sus propios vales; campo Responsable muestra nombre real
- ✅ Cajas: Mecánico solo ve su caja asignada; puede solicitar mantención pero no auditar
- ✅ Mantenimiento: Mecánico no accede a documentos adjuntos
- ✅ Reportes: módulo bloqueado para Mecánico (requiere Encargado o Jefe)
- ✅ Usuarios: Mecánico puede ver pero no editar su perfil
- ✅ Menú lateral: Personalización y Tablas maestras ocultos para Mecánico
- ✅ Migración Alembic: estado `mantenimiento_solicitada` + campos adicionales en Tool

### Identificación física por color de mecánico
- ✅ Color identificador asignado a cada mecánico, visible en UI y en sus préstamos
- ✅ Permite marcar herramientas y cajas físicamente en el taller por mecánico

### Autenticación por RUT chileno
- ✅ RUT como identificador único de login (reemplaza email como campo de login)
- ✅ Email sigue existiendo pero es editable y no autentica
- ✅ Validación de dígito verificador de RUT (`app/core/rut.py`)
- ✅ Datos de demo: RUT 1-9 (Jefe) / 2-7 (Encargado) / 3-5 (Mecánico), contraseña Admin123!

---

## 2026-08-13

### Rebranding a Pañol 360 y mejoras de UI
- ✅ Nombre del producto: "Pañol 360" (antes "Pañol v2"); logo propio en sidebar
- ✅ Logo del cliente en el topbar (coexistencia white-label: marca del producto + marca del cliente)
- ✅ Título de página con subtítulo dinámico según contexto de cada pantalla
- ✅ Sidebar colapsable en desktop con estado persistido en localStorage

### Mejoras de módulos
- ✅ Herramientas: duplicar herramienta, código de producto, múltiples números de serie
- ✅ Herramientas: folio y adjunto del documento de compra (PDF, imagen)
- ✅ Herramientas: CSV de ejemplo descargable para usar como plantilla de importación
- ✅ Herramientas: valores económicos (costo, depreciación) ocultos para roles no-Jefe
- ✅ Préstamos: vale PDF con visor in-app + botón de descarga (igual que Mantenimiento)
- ✅ Préstamos: tooltip con color por urgencia (verde ≤3 días / naranja ≤7 / rojo vencido)
- ✅ Mantenimiento: título y observación por documento; múltiples archivos adjuntos por registro
- ✅ Proveedores: campos dirección, teléfono, email, contacto y RUT

### Datos y correcciones de infraestructura
- ✅ Datos de ejemplo regenerados coherentes con todas las fases (herramientas, préstamos, cajas, usuarios)
- 🔧 Backend en bucle de reinicio: CRLF rompía shebang del entrypoint → convertido a LF
- 🔧 Alembic vs `create_tables()`: race condition al arrancar → orden de ejecución corregido
- 🔧 `pg_dump` version mismatch en módulo de Respaldo → binario correcto de PostgreSQL 16
- 🔧 Footer de la app con datos del desarrollador (nombre, teléfono, email)

---

## 2026-08-12

### Core del sistema — Fases 1 a 7

**Fase 1 — Sesión real y UX base**
- ✅ JWT en localStorage; HTMX adjunta `Authorization` en cada request automáticamente
- ✅ Notificaciones de préstamos vencidos en el topbar
- ✅ KPIs del dashboard clickeables (navegan al módulo correspondiente)
- ✅ Cajas: mecánico responsable asignado; al agregar herramientas filtra solo las disponibles

**Fase 2 — Tablas maestras**
- ✅ Modelos: Marca, Categoría, Ubicación, Proveedor con CRUD completo vía HTMX
- ✅ UI de administración con formularios inline
- ✅ Formulario de herramientas con dropdowns vinculados a tablas maestras
- ✅ Nuevo estado de herramienta: "en caja de herramientas"

**Fase 3 — Mantenimiento y baja de herramientas**
- ✅ Módulo de mantenimiento con historial, documentos adjuntos y registro de costos
- ✅ Dar de baja definitiva a herramientas con motivo y observación
- ✅ Acción rápida "Enviar a mantenimiento" desde listado de Herramientas
- ✅ Devolución con daño engancha automáticamente a Mantenimiento

**Fase 4 — Auditoría de cajas**
- ✅ Auditoría de inventario por caja: compara contenido registrado vs real
- ✅ Historial de auditorías con resultados y diferencias detectadas

**Fase 5 — Importación / exportación masiva**
- ✅ Exportar catálogo de herramientas a CSV
- ✅ Importar herramientas desde CSV con validación fila por fila y reporte de errores
- ✅ Carga masiva de préstamos tipo planilla CSV

**Fase 6 — Reportes extendidos**
- ✅ Reporte de inventario: depreciación, estado, ubicación, proveedor por herramienta
- ✅ Reporte de préstamos: historial completo con métricas de uso por herramienta/mecánico
- ✅ Reporte de Mantenimiento: costos acumulados y tiempos promedio de reparación

**Fase 7 — Funcionalidades avanzadas**
- ✅ Foto de perfil de usuario: upload y visualización en sidebar y topbar
- ✅ Backup integral desde la UI: dump PostgreSQL + archivos estáticos en ZIP descargable
- ✅ Restaurar backup desde la UI con validación
- ✅ Indicadores económicos de Chile en el header: USD, UF, EUR, UTM (API `mindicador.cl`)

### Infraestructura base y PWA
- ✅ PWA instalable: `manifest.json` + Service Worker con caché offline para vendor JS/CSS/íconos
- ✅ Página offline cuando no hay conexión (en vez del error genérico del navegador)
- ✅ Notificaciones push del navegador para préstamos vencidos
- ✅ Escaneo de QR por cámara en Herramientas (`qr-scanner.js`, sin librerías externas)
- ✅ 2FA (TOTP) opt-in: login en dos pasos compatible con Google Authenticator y Authy
- ✅ JS/CSS vendorizados en `static/vendor/` (sin dependencia de CDNs, funciona sin internet)
- ✅ `auth.js` centraliza: token en localStorage, adjunta header a HTMX y fetch, redirige al expirar
- ✅ Docker build estabilizado: Debian bookworm pinneado, dependencias depuradas

---

## 2026-08-11

### Desarrollo inicial de Pañol v2.0
- ✅ FastAPI 0.110 + SQLAlchemy 2.0 async + Alembic para migraciones de base de datos
- ✅ PostgreSQL 16 + Redis 7 + Celery 5 para tareas asíncronas
- ✅ Autenticación JWT (python-jose) con OAuth2 Password Flow y bcrypt
- ✅ Módulos core: Herramientas, Préstamos, Cajas, Reportes, Usuarios
- ✅ Vale de préstamo PDF imprimible con firma (`pdf_service.py`)
- ✅ Frontend: HTMX 2 + Alpine.js 3 + Tailwind CSS 4 (sin React/Vue/Angular)
- ✅ Sistema de branding dinámico: CSS custom properties + subida de logo drag & drop + color picker HSL
- ✅ Branding persistido en PostgreSQL (`brand_configs`); cambios visibles sin reload de página
- ✅ Generación de código QR por herramienta (`qr_service.py`)
- ✅ Docker Compose: PostgreSQL + Redis + FastAPI + Nginx como reverse proxy

---


---

# 📋 Pendientes y próximos pasos

> Estado al 2026-09-03 (tarde). Actualizar a medida que se completen.

## 🔴 Crítico — sin esto el sistema no está completo en producción

| # | Tarea | Detalle |
|---|-------|---------|
| 1 | **Instalar Tailscale en el servidor** | `curl -fsSL https://tailscale.com/install.sh \| sh && sudo tailscale up` — sin esto el admin panel en :9001 no es accesible de forma segura |
| 2 | **Configurar contraseña del admin panel** | Generar hash bcrypt, actualizar `ADMIN_PANEL_PASSWORD_HASH` en `.env` del servidor, `docker compose restart admin-panel` |
| 3 | **Instalar Tailscale en dispositivos del equipo** | PC de administración + celulares que usarán el admin panel |

## 🟡 Importante — mejoras de producto pendientes

| # | Estado | Tarea | Detalle |
|---|--------|-------|---------|
| 4 | ✅ | **Notificaciones de préstamos vencidos por email** | `notification_service.py` implementado; task Celery `mark_overdue_loans` envía aviso al vencer |
| 5 | ✅ | **Reportes: exportar a PDF** | Botón ⬇ PDF en las 3 pestañas; `report_pdf_service.py` genera PDF A4 con branding |
| 6 | ✅ | **Módulo de depreciación** | `depreciation.py` implementado y conectado a la UI de Reportes de Inventario |
| 7 | ✅ | **Dashboard: gráfico de uso por categoría** | Query real a la BD; datos reales en Chart.js |
| 8 | ✅ | **Herramientas: alerta de stock mínimo** | Campo `min_stock` en Tool; badge ⚠ en tabla; aviso por email al prestar si el stock cae bajo el mínimo |
| 9 | ✅ | **Préstamos: recordatorio antes de vencer** | Task Celery `send_loan_reminders` avisa 1 día antes; corre a 08:00 UTC (11:00 Chile) |

## 🟢 Nice-to-have — para versiones futuras

| # | Tarea | Detalle |
|---|-------|---------|
| 10 | **App móvil nativa (Android/iOS)** | Hoy funciona como PWA instalable; una app nativa mejoraría la cámara QR y notificaciones push |
| 11 | **Historial de ubicación de herramienta** | Trazabilidad completa: quién tuvo la herramienta, cuándo y en qué proyecto |
| 12 | **Integración con otros clientes SaaS** | El admin panel ya lee `clients/`; falta el flujo de onboarding para crear un cliente nuevo desde cero (crear directorios, configurar subdomain, deploy aislado) |
| 13 | **Mapa de ubicaciones** | Visualización de dónde están las herramientas en el plano del taller (drag & drop) |
| 14 | **Estadísticas de uso para SaaS** | Métricas agregadas en el admin panel: herramientas prestadas por cliente, logins, errores |

## ✅ Deuda técnica a resolver

| # | Tarea | Detalle |
|---|-------|---------|
| 15 | **Merge a `main` del branch de desarrollo** | Todo el trabajo está en `claude/develop-zip-file-nlfvlt`; hacer PR y merge a main |
| 16 | **Suite de tests automatizados** | Los tests Playwright de los 3 roles quedaron en el commit de Fase 7; verificar que corren en CI |
| 17 | **Renovación de certificado SSL** | Certbot está configurado con cron; verificar que el primer auto-renewal funcione correctamente |
| 18 | **Monitoreo de errores** | UptimeRobot cubre el uptime; falta capturar errores de la app (Sentry o similar) |
