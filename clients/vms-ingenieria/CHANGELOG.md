# Bitácora de Cambios — VMS Ingeniería

> Registro cronológico de todos los cambios aplicados a este cliente.
> Agregar entradas con: `bash scripts/admin.sh log vms-ingenieria "descripción"`

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
