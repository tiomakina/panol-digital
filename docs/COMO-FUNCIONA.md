# Cómo funciona Pañol 360 — Guía de control total

> Este documento es **tu manual de referencia**. Si alguna vez te perdés de lo que estamos
> haciendo, empezá acá. Está escrito en lenguaje simple, sin jerga técnica innecesaria.

---

## 1. La arquitectura — qué hay y cómo se comunica

```
INTERNET
   │
   ▼
┌─────────────────────────────────────────────────────────┐
│  Oracle Cloud — Servidor Ubuntu 24.04 (146.181.45.138)  │
│                                                         │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────┐  │
│  │  Nginx   │───▶│ FastAPI  │───▶│  PostgreSQL 16   │  │
│  │ :80/:443 │    │  :8000   │    │  (base de datos) │  │
│  └──────────┘    └──────────┘    └──────────────────┘  │
│       │               │          ┌──────────────────┐  │
│  SSL Let's        Jinja2 +       │    Redis 7        │  │
│  Encrypt          HTMX +         │  (caché/Celery)  │  │
│                  Alpine.js       └──────────────────┘  │
│                                  ┌──────────────────┐  │
│                                  │  Celery Worker   │  │
│                                  │  (tareas async)  │  │
│                                  └──────────────────┘  │
│                                  ┌──────────────────┐  │
│                                  │  Portainer CE    │  │
│                                  │  (solo localhost) │  │
│                                  └──────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

**En palabras simples:**
- El usuario abre el navegador → llega a Nginx
- Nginx decide: ¿es un archivo estático (CSS/JS/imagen)? → lo sirve directo
- ¿Es una página o llamada API? → lo pasa al backend (FastAPI)
- FastAPI lee/escribe en PostgreSQL y usa Redis para caché
- Celery procesa tareas en segundo plano (emails, recordatorios)
- Todo corre dentro de **contenedores Docker** — son como "cajas" aisladas

---

## 2. Docker — la base de todo

Docker es lo que hace que el sistema funcione igual en cualquier servidor.
En vez de instalar Python, PostgreSQL, etc. directamente, todo corre en contenedores.

### Los 7 contenedores del sistema

| Nombre | Qué hace | Puerto visible |
|--------|----------|----------------|
| `nginx` | Recibe el tráfico web, SSL | 80 y 443 (internet) |
| `backend` | FastAPI — la aplicación | Solo interno (8000) |
| `db` | PostgreSQL — base de datos | Solo interno (5432) |
| `redis` | Caché y cola de tareas | Solo interno (6379) |
| `celery_worker` | Ejecuta tareas async | Ninguno |
| `celery_beat` | Dispara tareas periódicas | Ninguno |
| `portainer` | Panel visual Docker | 9000 (solo SSH tunnel) |

### Comandos Docker que usás

```bash
# Ver qué contenedores están corriendo y su estado
sudo docker compose ps

# Ver los logs en tiempo real
sudo docker compose logs -f backend

# Reiniciar un contenedor (sin reconstruir)
sudo docker compose restart backend

# Reconstruir y reiniciar (cuando cambia el código)
sudo docker compose up -d --build backend

# Apagar todo
sudo docker compose down

# Levantar todo
sudo docker compose up -d
```

---

## 3. El flujo de desarrollo — cómo se hacen los cambios

```
TU MÁQUINA               GITHUB               SERVIDOR
     │                      │                     │
     │  1. Abrís Claude Code │                     │
     │  2. Pedís un cambio   │                     │
     │  3. Claude edita      │                     │
     │     los archivos      │                     │
     │                       │                     │
     │── git push ──────────▶│                     │
     │                       │                     │
     │                       │── git pull ─────────▶│
     │                       │                     │ (en el servidor)
     │                       │                     │── docker compose
     │                       │                     │   up -d --build
     │                       │                     │
     │                       │                     │ ✅ Cambio aplicado
```

### Los dos tipos de cambio

**Cambio de código** (requiere reconstruir la imagen Docker):
```bash
# En el servidor:
git pull origin main
sudo docker compose up -d --build backend
```
> Cuándo: cuando cambia cualquier archivo `.py`, `.html`, `.css`, `.js`

**Cambio de configuración** (solo restart):
```bash
# En el servidor:
git pull origin main
sudo docker compose restart backend
```
> Cuándo: cuando cambia `.env` o `brand_config.json`

**Cambio de nginx** (reload de nginx):
```bash
# En el servidor:
git pull origin main
sudo docker compose exec nginx nginx -s reload
```
> Cuándo: cuando cambia `nginx.conf`

---

## 4. El modelo de clientes — cómo funciona el SaaS

Pañol 360 usa el modelo **"Un deployment por cliente"**.
Cada cliente es una copia independiente del sistema en su propio directorio del servidor.

```
/home/ubuntu/
├── panol-digital/          ← VMS Ingeniería (el demo)
│   ├── docker-compose.yml
│   ├── .env                ← secrets de VMS
│   └── backend/
│
└── clients/
    ├── taller-vms/         ← Taller VMS (futuro cliente)
    │   ├── docker-compose.yml
    │   ├── .env            ← secrets del taller
    │   └── backend/
    │
    └── constructora-xyz/   ← Otro cliente
        └── ...
```

**¿Por qué este modelo?**
- Datos 100% aislados (si un cliente tiene un problema, los otros no se ven afectados)
- Si un cliente paga más, le das más recursos
- Actualizaciones controladas — podés actualizar un cliente sin tocar los demás
- Más simple de implementar y mantener

**¿Cómo se diferencia cada cliente?**
- Su propio subdominio: `panol.vmsingenieria.cl`, `panol.tallervms.cl`
- Su propio archivo `.env` con su contraseña de BD, sus secrets
- Su propio `brand_config.json` con su logo y colores
- Su propia base de datos PostgreSQL (en el mismo servidor pero separada)

---

## 5. El repositorio Git — cómo está organizado

```
panol-digital/              ← Código fuente del sistema (compartido entre clientes)
├── CLAUDE.md               ← Instrucciones para Claude Code
├── CHANGELOG.md            ← Bitácora global de cambios del sistema
├── SESSION.md              ← Contexto actual de trabajo (gitignoreado)
│
├── backend/                ← El código de la aplicación
│   ├── app/
│   │   ├── main.py         ← Punto de entrada de FastAPI
│   │   ├── api/v1/         ← Los endpoints de la API
│   │   ├── models/         ← Tablas de la base de datos
│   │   ├── templates/      ← Páginas HTML (Jinja2)
│   │   └── static/         ← CSS, JS, imágenes
│   └── requirements.txt    ← Dependencias Python
│
├── clients/                ← Registro de clientes (configs y bitácoras)
│   ├── README.md
│   └── vms-ingenieria/
│       ├── client.conf     ← Datos del cliente
│       └── CHANGELOG.md    ← Bitácora de cambios de ese cliente
│
├── scripts/
│   ├── admin.sh            ← Consola de administración ← USÁ ESTO
│   ├── backup.sh           ← Backup manual
│   └── restore.sh          ← Restaurar backup
│
├── docs/
│   └── COMO-FUNCIONA.md    ← Este archivo
│
├── nginx.conf              ← Configuración del servidor web
└── docker-compose.yml      ← Definición de los contenedores
```

---

## 6. Las ramas de Git — dev vs producción

```
main ──────────────────────────────────────────▶  PRODUCCIÓN
  └── claude/develop-zip-file-nlfvlt ──────────▶  DESARROLLO
```

| Rama | Propósito | Se hace push acá cuando... |
|------|-----------|---------------------------|
| `main` | Producción — lo que está en el servidor | El cambio está probado y listo |
| `claude/develop-*` | Desarrollo — donde Claude trabaja | Claude hace los cambios |

**Flujo estándar:**
1. Claude trabaja en la rama de desarrollo
2. Cuando está listo: merge a `main`
3. En el servidor: `git pull origin main` + rebuild

---

## 7. Cómo trabajar con Claude Code sin perder el hilo

### Al inicio de cada sesión
1. Decile a Claude en qué cliente estás trabajando:
   ```
   bash scripts/admin.sh context vms-ingenieria prod
   ```
   Esto actualiza `SESSION.md` y yo lo leo automáticamente.

2. O si es algo nuevo del sistema (no específico de un cliente):
   ```
   bash scripts/admin.sh context sistema dev
   ```

### Cómo pedirle cambios a Claude
Sé específico sobre el contexto:
- ✅ "En el módulo de Herramientas, quiero agregar un campo 'Garantía'"
- ✅ "Para el cliente VMS Ingeniería, cambiar el color primario a verde"
- ✅ "Es un cambio de producción, necesito que funcione hoy"
- ❌ "Cambiá el sistema" (muy vago)

### Qué hace Claude y qué hacés vos
| Claude hace | Vos hacés |
|-------------|-----------|
| Editar código, crear archivos | Aprobar cambios en Claude Code |
| Hacer commits y push a GitHub | Correr `git pull` en el servidor |
| Decirte qué comandos correr | Correr los comandos en el server |
| Documentar en CHANGELOG | Confirmar que funcionó |

---

## 8. La base de datos — qué pasa si algo se rompe

La base de datos vive en un volumen Docker (`postgres_data`).
Si borrás el volumen, perdés los datos. **No borres volúmenes en producción.**

### Comandos de emergencia

```bash
# Ver cuánto espacio usa la BD
sudo docker compose exec db psql -U panol -d panol_db -c "SELECT pg_size_pretty(pg_database_size('panol_db'));"

# Entrar a la BD (modo interactivo)
sudo docker compose exec db psql -U panol -d panol_db

# Ver todas las tablas
\dt

# Salir de psql
\q

# Hacer un backup de emergencia
bash scripts/backup.sh

# Ver los backups disponibles
ls -lh backups/
```

---

## 9. SSL (HTTPS) — el candado verde del navegador

Let's Encrypt emite certificados gratuitos que duran 90 días.
Un cron configurado en el servidor los renueva automáticamente a las 03:00.

```bash
# Ver cuándo vence el certificado
sudo certbot certificates

# Forzar renovación manual (si algo falló)
sudo certbot renew --force-renewal --webroot --webroot-path /var/www/certbot

# Verificar que el cron está configurado
sudo crontab -l
```

---

## 10. Portainer — el panel visual de Docker

Portainer es una interfaz web para ver y gestionar los contenedores Docker visualmente.
Por seguridad, solo es accesible desde tu computadora mediante un túnel SSH.

```bash
# Abrir el túnel (correr en tu máquina local, NO en el servidor)
ssh -i "tu_clave.key" -L 9000:localhost:9000 ubuntu@146.181.45.138

# Luego abrir en el navegador:
# http://localhost:9000
```

---

## 11. Monitoreo — UptimeRobot

UptimeRobot chequea cada 5 minutos si el sistema responde.
Si hay un problema, te manda un email y una notificación push.

- Dashboard: https://dashboard.uptimerobot.com
- Endpoint monitoreado: `https://demopanol.valentinmorales.cl/health`
- Qué hace `/health`: responde `ok` si el backend está vivo

---

## Glosario rápido

| Término | Qué es |
|---------|--------|
| **Docker** | Sistema que "empaqueta" la aplicación para que funcione igual en cualquier server |
| **Contenedor** | Una "caja" Docker que corre un proceso (nginx, backend, bd, etc.) |
| **Volumen** | Almacenamiento persistente de Docker (los datos de la BD viven acá) |
| **FastAPI** | El framework Python que procesa las requests y sirve las páginas |
| **HTMX** | Biblioteca JS mínima que hace las páginas interactivas sin JavaScript complejo |
| **Alembic** | Herramienta que aplica cambios a la estructura de la base de datos |
| **JWT** | Token de autenticación que se guarda en el navegador — identifica al usuario logueado |
| **Celery** | Sistema de tareas en segundo plano (enviar emails, procesar archivos grandes) |
| **Redis** | Base de datos ultrarrápida usada para caché y la cola de Celery |
| **Nginx** | Servidor web que recibe el tráfico y lo distribuye (también sirve los archivos estáticos) |
| **SSL/TLS** | El "candado verde" del navegador — cifra la comunicación |
| **Let's Encrypt** | Servicio gratuito que emite certificados SSL |
| **Branch/Rama** | Versión paralela del código en Git |
| **Commit** | Un "guardado" del estado del código con un mensaje descriptivo |
| **Push** | Subir los commits a GitHub |
| **Pull** | Bajar los commits de GitHub al servidor |
