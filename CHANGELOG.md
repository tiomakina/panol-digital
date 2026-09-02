# Changelog Global — Pañol 360

> Cambios al sistema base (código fuente compartido entre todos los clientes).
> Los cambios específicos de cada cliente van en `clients/<slug>/CHANGELOG.md`.

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
