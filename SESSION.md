# SESSION.md — Pañol 360

## Contexto activo
- **Cliente:** SaaS multi-tenant (admin general)
- **Entorno:** Producción
- **Servidor:** HP ProLiant ML110 G7 — Ubuntu 26.04.1 LTS
- **LAN IP:** 10.10.80.20
- **Tailscale IP servidor:** 100.82.18.120
- **Acceso remoto:** SSH via Tailscale desde cualquier lugar

---

## Acceso a paneles de administración

### Admin Panel (Pañol 360)
```
ssh -L 9001:localhost:9001 -L 9000:localhost:9000 ubuntu@100.82.18.120 -N
→ http://localhost:9001
```
Usar el archivo `abrir_admin_panel.bat` en el notebook para abrir el túnel automáticamente.

### Portainer (gestión Docker)
```
(mismo túnel que arriba)
→ http://localhost:9000
```

---

## Stack en producción

| Servicio | Estado | Puerto |
|---|---|---|
| backend (FastAPI) | UP | interno |
| backend-staging | UP | interno |
| nginx | UP | 80/443 públicos |
| db (PostgreSQL 16) | UP healthy | interno |
| redis | UP | interno |
| celery_worker | UP | interno |
| celery_beat | UP | interno |
| admin-panel | UP healthy | 127.0.0.1:9001 |
| portainer | UP | 127.0.0.1:9000 |
| evolution-api (WAHA) | UP | interno |

---

## Historial de sesiones

### 2026-11-16 — QA completo + fixes de seguridad + acceso remoto

**QA realizado:** Revisión completa del sistema con 3 Alto / 5 Medio / 4 Bajo / 17 OK.

**3 vulnerabilidades altas corregidas** (commit `42d0346` → merge `9285ade` a main):

1. **Admin panel expuesto a toda la LAN**
   - `docker-compose.yml`: cambio de `"9001:9001"` a `"127.0.0.1:9001:9001"`
   - Ahora solo accesible via túnel SSH

2. **Staging enrutando al backend de producción**
   - `nginx.conf`: upstream staging era `http://backend:8000` → corregido a `http://backend-staging:8000`
   - HSTS añadido al bloque staging

3. **IP spoofing en rate limit**
   - `backend/app/core/rate_limit.py`: eliminado fallback `X-Forwarded-For` falsificable
   - Ahora solo usa `X-Real-IP` seteado por Nginx (no falsificable)

**Acceso remoto configurado:**
- Tailscale ya estaba instalado en el servidor (IP: 100.82.18.120)
- Creado `abrir_admin_panel.bat` para acceso desde notebook via Tailscale
- Portainer configurado por primera vez

---

## Pendientes técnicos

### Prioridad Media — COMPLETADOS 2026-11-16
- [x] **Redis con autenticación** — `--requirepass` en `docker-compose.yml`, `REDIS_PASSWORD` en `.env` del servidor con contraseña aleatoria `openssl rand -hex 32`
- [x] **Chequeo explícito de tenant en `get_current_user()`** — validación `user.tenant_id == current_tenant` en `security.py`
- [x] **Limpiar fotos huérfanas** — `unlink(missing_ok=True)` antes de guardar nueva foto en `tools.py` y `users.py`

### Prioridad Baja
- [ ] **SMTP FROM address** — cambiar a `info@valentinmorales.cl` (requiere alias Gmail primero)
- [ ] **Módulo Ayuda** — diferenciar contenido por rol (jefe / encargado / mecánico)

---

## Credenciales de prueba
Login con **RUT** + contraseña:
```
Admin (Jefe):    RUT 1-9  / Admin123!
Encargado:       RUT 2-7  / Admin123!
Mecánico:        RUT 3-5  / Admin123!
```

## Dominios
- Producción: https://panol360.app
- Staging: https://staging.panol360.app
