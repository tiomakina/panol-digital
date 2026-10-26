# Changelog Global — Pañol 360

> Cambios al sistema base (código fuente compartido entre todos los clientes).
> Los cambios específicos de cada cliente van en `clients/<slug>/CHANGELOG.md`.

---

## [2.2.0] — 2026-10-26

### Seguridad (auditoría completa)
- `nginx.conf`: bloqueo a nivel Nginx de `/api/v1/admin/`, `/api/docs`, `/api/redoc`, `/openapi.json` en producción y staging — rutas internas no expuestas públicamente
- `core/rate_limit.py`: detección de IP real via `X-Real-IP` → `X-Forwarded-For` → `request.client.host`
- `services/brand_service.py`: SVG eliminado de tipos de archivo permitidos en uploads (previene XSS embebido)
- `api/v1/reports.py`: endpoints de exportación de inventario requieren rol `jefe` (RBAC corregido)
- `api/v1/admin_api.py`: path traversal corregido con `Path.resolve()` + validación de columnas JSON contra regex `[a-zA-Z0-9_]+` (previene SQL injection)
- `main.py`: cookies `panol_tenant` con `httponly=True` en `/demo` y `/portal/verify`
- `schemas/user.py`: política de contraseñas — mínimo 10 caracteres, mayúscula, minúscula y número en `UserCreate` y `PasswordChange`
- `api/v1/users.py`: función `_client_ip()` para registro de IP real en auditoría
- `admin-panel/main.py`: rate limiting en login — 5 intentos por IP cada 5 minutos (in-memory)
- `models/tenant_mixin.py`: eliminado `default="vms-ingenieria"` del campo `tenant_id`

### Infraestructura
- Servidor actualizado: Ubuntu 24.04.5 LTS, kernel 7.0.0-1013-oracle, Docker 29.9.2
- `scripts/monthly-maintenance.sh`: mantenimiento mensual automatizado (backup + apt upgrade + limpieza Docker)
- `scripts/send_maintenance_email.py`: email HTML de resumen con estado de cada paso y fecha del próximo mantenimiento
- `scripts/.maintenance-email.conf.example`: plantilla de credenciales SMTP (el `.conf` real vive solo en el servidor)
- Cron configurado: día 26 de cada mes, 01:00 AM (America/Santiago)

---

## [2.1.0] — 2026-09-02

### Seguridad
- Actualización de dependencias Python: 59 CVEs resueltos
  - python-multipart 0.0.31, python-jose 3.4.0, jinja2 3.1.6
  - Pillow 12.3.0, aiosmtplib 5.1.2, python-dotenv 1.2.2
- pytest downgrade a 8.3.5 (pytest-asyncio incompatible con pytest ≥ 9)

### Infraestructura
- docker-compose.yml: eliminado atributo `version` obsoleto
- Portainer: flag `--no-setup-token` + puerto restringido a 127.0.0.1
- PostgreSQL y Redis: solo expuestos en red interna Docker

### Nuevas features
- Endpoint `/health` (GET + HEAD) para monitoreo externo sin autenticación
- Íconos PWA: icon-192.png (192×192) + icon-512.png (512×512)
- Página 404 personalizada con branding dinámico (catch-all route)
- `scripts/setup_production.sh`: configura secrets, certbot y crons en un comando
- `scripts/admin.sh`: consola de administración de clientes

### Sistema de control
- `clients/`: directorio de registro de clientes con bitácoras individuales
- `CHANGELOG.md`: este archivo — bitácora global del sistema
- `docs/COMO-FUNCIONA.md`: documentación completa del sistema
- `SESSION.md` (gitignoreado): contexto de sesión para Claude Code
- Actualización de CLAUDE.md con instrucciones de contexto de cliente

### Correcciones
- backup.sh / restore.sh: parseo seguro de .env sin `source` (fix para archivos
  con caracteres especiales como ñ en comentarios con `set -euo pipefail` activo)

---

## [2.0.0] — 2026-08 (baseline)

Sistema base: FastAPI + PostgreSQL + Redis + Celery + Nginx + Portainer.
Ver historial de commits en GitHub para el detalle completo.
