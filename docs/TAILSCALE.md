# 🔒 Admin Panel vía Tailscale VPN

Guía paso a paso para acceder al panel de administración de Pañol 360
desde cualquier dispositivo (PC, iPhone, Android) sin exponer ningún puerto
a internet.

---

## ¿Qué es Tailscale?

Tailscale crea una red privada (VPN mesh) cifrada con WireGuard entre tus
dispositivos. Una vez instalado, el servidor y tu celular aparecen en la misma
red privada `100.x.x.x` — aunque estén en distintos países.

**Gratis para hasta 100 dispositivos. Sin configuración de routers ni puertos.**

---

## Arquitectura de seguridad

```
Internet público
       │
       ├─ demopanol.valentinmorales.cl:80/443  → Nginx → Backend (PÚBLICO ✓)
       │
       └─ Puerto 9001  → BLOQUEADO por Oracle Cloud Security List ✗

Tailscale VPN (100.x.x.x)
       │
       └─ 100.x.x.x:9001  → Admin Panel (SOLO VPN ✓)
                              ├─ Autenticación: usuario + contraseña bcrypt
                              └─ Sesión cifrada (Tailscale WireGuard)
```

---

## PASO 1 — Instalar Tailscale en el servidor Oracle Cloud

```bash
# Conectarse al servidor
ssh ubuntu@146.181.45.138

# Instalar Tailscale (una sola línea)
curl -fsSL https://tailscale.com/install.sh | sh

# Autenticar el servidor (abre el link en tu navegador)
sudo tailscale up

# Verificar que Tailscale está corriendo y obtener la IP privada
tailscale ip -4
# → Ejemplo: 100.98.47.23  ← guarda este número
```

Tailscale abrirá una URL para autenticar. Iníciala en tu navegador, entra con
tu cuenta de Google/GitHub, y el servidor quedará conectado a tu red Tailscale.

---

## PASO 2 — Configurar el Admin Panel en el servidor

```bash
# En el servidor, ir al directorio del proyecto
cd ~/panol-digital

# Generar la contraseña del panel
python3 -c "import bcrypt; pw=input('Contraseña: ').encode(); print(bcrypt.hashpw(pw, bcrypt.gensalt()).decode())"

# Editar el .env y agregar las 3 variables del Admin Panel
nano .env
```

Agregar al final del `.env`:
```env
ADMIN_PANEL_USER=admin
ADMIN_PANEL_PASSWORD_HASH=$2b$12$...  ← el hash generado arriba
ADMIN_PANEL_SECRET=$(openssl rand -hex 32)
```

---

## PASO 3 — Levantar el Admin Panel

```bash
cd ~/panol-digital

# Traer el código más reciente
git fetch origin
git checkout origin/claude/develop-zip-file-nlfvlt -- admin-panel/ docker-compose.yml .env.example

# Levantar solo el admin-panel (sin tocar los demás servicios)
docker compose up -d admin-panel

# Verificar que está corriendo
docker compose ps admin-panel
# → admin-panel   running   0.0.0.0:9001->9001/tcp
```

---

## PASO 4 — Configurar el firewall (UFW) en el servidor

Oracle Cloud ya bloquea el puerto 9001 desde internet (Security List). 
Este paso es adicional para que solo Tailscale pueda acceder:

```bash
# Permitir acceso al port 9001 SOLO desde la red Tailscale (CGNAT 100.64.0.0/10)
sudo ufw allow from 100.64.0.0/10 to any port 9001 comment "Admin Panel - Tailscale only"

# Verificar
sudo ufw status | grep 9001
```

---

## PASO 5 — Acceder desde Android

### Instalar Tailscale en el celular

1. Abre **Play Store** → busca **Tailscale** (desarrollador: Tailscale Inc.)
2. Instálala y ábrela
3. Toca **Iniciar sesión** → usa la misma cuenta Google/GitHub que usaste en el servidor
4. La app se conectará automáticamente a tu red privada

### Abrir el Admin Panel

Una vez conectado a Tailscale en tu celular:

```
http://100.98.47.23:9001
      ↑ IP Tailscale de tu servidor (la que viste en `tailscale ip -4`)
```

> **Tip:** Guarda esta URL como marcador en Chrome. También puedes agregarla
> a la pantalla de inicio como PWA: menú ⋮ → "Agregar a pantalla de inicio"

---

## PASO 6 — Acceder desde PC / Mac

```bash
# Instalar Tailscale en tu computadora
# Mac: brew install tailscale
# Windows: descargar desde tailscale.com/download
# Linux: curl -fsSL https://tailscale.com/install.sh | sh

# Autenticar con la misma cuenta
sudo tailscale up

# Abrir el panel
open http://100.98.47.23:9001   # Mac
# Windows: abrir en el navegador
```

---

## Verificación rápida

```bash
# Desde cualquier dispositivo Tailscale, verificar que el panel responde
curl http://100.98.47.23:9001/health
# → {"status": "ok", "version": "1.0.0"}
```

---

## Comandos útiles

```bash
# Ver qué dispositivos están conectados a tu red Tailscale
tailscale status

# Ver la IP del servidor en Tailscale
tailscale ip -4

# Ver logs del Admin Panel
docker compose logs -f admin-panel

# Reiniciar el Admin Panel
docker compose restart admin-panel

# Ver estado del panel
docker compose ps admin-panel
```

---

## Seguridad: qué está protegido y cómo

| Capa | Protección |
|------|-----------|
| Oracle Cloud Security List | Puerto 9001 no habilitado → nadie de internet puede conectarse |
| Tailscale WireGuard | Todo el tráfico cifrado end-to-end (ChaCha20Poly1305) |
| UFW | Solo acepta conexiones desde 100.64.0.0/10 (rango Tailscale) |
| Admin Panel auth | Usuario + contraseña bcrypt (hash irreversible) |
| Sesión | Cookie firmada con clave secreta aleatoria, expira en 8 horas |
| Panel "read-only" | El panel no ejecuta comandos shell — solo muestra comandos para copiar |

---

## Solución de problemas

### No puedo acceder a `http://100.x.x.x:9001`

1. Verifica que Tailscale está activo en el servidor: `tailscale status`
2. Verifica que el contenedor está corriendo: `docker compose ps admin-panel`
3. Verifica que Tailscale está activo en tu celular (icono verde en la app)
4. Prueba el health check: `curl http://100.x.x.x:9001/health`

### El panel muestra "lista de clientes vacía"

El volumen `./clients:/app/clients` debe existir en el servidor:
```bash
ls ~/panol-digital/clients/
bash scripts/admin.sh list
```

### Olvidé la contraseña del panel

```bash
# En el servidor, generar nueva contraseña y actualizar .env
cd ~/panol-digital
python3 -c "import bcrypt; pw=input('Nueva contraseña: ').encode(); print(bcrypt.hashpw(pw, bcrypt.gensalt()).decode())"
# Editar .env → ADMIN_PANEL_PASSWORD_HASH=<nuevo hash>
docker compose restart admin-panel
```

---

*Ver también: `docs/COMO-FUNCIONA.md` para arquitectura completa del sistema.*
