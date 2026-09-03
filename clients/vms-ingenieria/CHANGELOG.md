# Bitácora de Cambios — VMS Ingeniería

> Registro cronológico de todos los cambios aplicados a este cliente.
> Agregar entradas con: `bash scripts/admin.sh log vms-ingenieria "descripción"`

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
