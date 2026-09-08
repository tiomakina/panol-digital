#!/usr/bin/env python3
"""
Pañol 360 — Admin Panel
Panel de administración de clientes SaaS.
Acceso exclusivamente vía Tailscale VPN.
"""
import json
import os
import re
import bcrypt
import httpx
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

# ─── Configuración ────────────────────────────────────────────────────────────
CLIENTS_DIR = Path(os.environ.get("CLIENTS_DIR", "/app/clients"))
TENANTS_FILE = Path(os.environ.get("TENANTS_FILE", "/app/tenants.json"))
BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")
ADMIN_API_SECRET = os.environ.get("ADMIN_API_SECRET", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "CAMBIAR_CON_openssl_rand_hex_32")
ADMIN_USER = os.environ.get("ADMIN_USERNAME", "admin")
# Hash bcrypt de la contraseña — generar con:
# python3 -c "import bcrypt; print(bcrypt.hashpw(b'TuPassword', bcrypt.gensalt()).decode())"
ADMIN_HASH_STR = os.environ.get("ADMIN_PASSWORD_HASH", "")
APP_TITLE = "Pañol 360 — Admin"
APP_VERSION = "1.0.0"

# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=APP_TITLE,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=28800,  # 8 horas
    https_only=False,  # Tailscale ya provee cifrado a nivel de red
    same_site="strict",
)

templates = Jinja2Templates(directory="/app/templates")


# ─── Helpers de autenticación ─────────────────────────────────────────────────

def is_authenticated(request: Request) -> bool:
    return request.session.get("authenticated") is True


def verify_password(plain: str) -> bool:
    if not ADMIN_HASH_STR:
        return False
    try:
        return bcrypt.checkpw(plain.encode(), ADMIN_HASH_STR.encode())
    except Exception:
        return False


# ─── Helpers de datos ─────────────────────────────────────────────────────────

def parse_conf(slug: str) -> dict:
    """Lee client.conf y retorna dict; strips inline comments y quotes."""
    conf_path = CLIENTS_DIR / slug / "client.conf"
    if not conf_path.exists():
        return {}
    data: dict = {}
    with open(conf_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            # Strip inline comments y trailing whitespace
            value = re.sub(r"\s*#[^\"']*$", "", value).strip()
            # Strip comillas
            value = value.strip('"').strip("'")
            # Solo variables UPPER_CASE
            if re.match(r"^[A-Z][A-Z0-9_]*$", key):
                data[key] = value
    return data


def list_clients() -> list:
    """Lista todos los clientes registrados en clients/."""
    clients = []
    if not CLIENTS_DIR.exists():
        return clients
    for entry in sorted(CLIENTS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        name_lower = entry.name.lower()
        if name_lower in ("readme.md", ".git", ".gitkeep"):
            continue
        if entry.name.startswith("."):
            continue
        conf = parse_conf(entry.name)
        if not conf:
            continue
        clients.append({
            "slug": entry.name,
            "name": conf.get("CLIENT_NAME", entry.name),
            "domain": conf.get("DOMAIN", ""),
            "status": conf.get("STATUS", "unknown").lower(),
            "plan": conf.get("PLAN", "?"),
            "server_ip": conf.get("SERVER_IP", ""),
            "ssh_user": conf.get("SSH_USER", "ubuntu"),
            "ssh_port": conf.get("SSH_PORT", "22"),
            "deploy_path": conf.get("DEPLOY_PATH", "~/panol-digital"),
            "renewal_date": conf.get("RENEWAL_DATE", ""),
            "monthly_price": conf.get("MONTHLY_PRICE", ""),
            "notes": conf.get("NOTES", ""),
        })
    return clients


def read_changelog(slug: str) -> str:
    path = CLIENTS_DIR / slug / "CHANGELOG.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def validate_slug(slug: str) -> bool:
    return bool(re.match(r"^[a-z0-9][a-z0-9-]{0,50}$", slug))


def status_color(status: str) -> str:
    colors = {
        "active": "#22c55e",
        "suspended": "#f59e0b",
        "cancelled": "#ef4444",
        "trial": "#3b82f6",
        "demo": "#8b5cf6",
    }
    return colors.get(status, "#6b7280")


# Registrar helper en Jinja2
templates.env.globals["status_color"] = status_color


# ─── Rutas ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return JSONResponse({"status": "ok", "version": APP_VERSION})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    if is_authenticated(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "title": APP_TITLE,
        "error": "",
        "next": next,
    })


@app.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form(default="/"),
):
    username = username.strip()[:64]
    password = password[:128]

    if username == ADMIN_USER and verify_password(password):
        request.session["authenticated"] = True
        request.session["user"] = username
        # Sanitizar redirect
        if not next.startswith("/") or "//" in next:
            next = "/"
        return RedirectResponse(next, status_code=302)

    return templates.TemplateResponse("login.html", {
        "request": request,
        "title": APP_TITLE,
        "error": "Usuario o contraseña incorrectos",
        "next": next,
    }, status_code=401)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/login?next=/", status_code=302)

    clients = list_clients()
    stats = {
        "total": len(clients),
        "active": sum(1 for c in clients if c["status"] == "active"),
        "demo": sum(1 for c in clients if c["status"] == "demo"),
        "suspended": sum(1 for c in clients if c["status"] in ("suspended", "cancelled")),
    }

    return templates.TemplateResponse("index.html", {
        "request": request,
        "title": APP_TITLE,
        "clients": clients,
        "stats": stats,
        "now": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "user": request.session.get("user", "admin"),
    })


@app.get("/client/{slug}", response_class=HTMLResponse)
async def client_detail(request: Request, slug: str, added: str = ""):
    if not is_authenticated(request):
        return RedirectResponse(f"/login?next=/client/{slug}", status_code=302)

    if not validate_slug(slug):
        raise HTTPException(status_code=400, detail="Slug inválido")

    conf = parse_conf(slug)
    if not conf:
        raise HTTPException(status_code=404, detail=f"Cliente '{slug}' no encontrado")

    changelog = read_changelog(slug)

    # Generar comandos de administración
    ip = conf.get("SERVER_IP", "IP_DEL_SERVIDOR")
    user = conf.get("SSH_USER", "ubuntu")
    port = conf.get("SSH_PORT", "22")
    path = conf.get("DEPLOY_PATH", "~/panol-digital")
    port_flag = f" -p {port}" if port != "22" else ""

    commands = {
        "SSH": f"ssh{port_flag} {user}@{ip}",
        "Deploy (git pull + rebuild)": (
            f'ssh{port_flag} {user}@{ip} '
            f'"cd {path} && git pull && docker compose up -d --build backend"'
        ),
        "Ver logs en vivo": f'ssh{port_flag} {user}@{ip} "cd {path} && docker compose logs -f backend"',
        "Backup manual": f'ssh{port_flag} {user}@{ip} "cd {path} && bash scripts/backup.sh"',
        "Shell en contenedor backend": f'ssh{port_flag} {user}@{ip} "docker exec -it panol-backend bash"',
        "Estado de contenedores": f'ssh{port_flag} {user}@{ip} "cd {path} && docker compose ps"',
        "Reiniciar todos": f'ssh{port_flag} {user}@{ip} "cd {path} && docker compose restart"',
        "Ver uso de disco": f'ssh{port_flag} {user}@{ip} "df -h && du -sh {path}/backups/ 2>/dev/null"',
        "Contexto Claude": f"bash scripts/admin.sh context {slug} prod",
    }

    return templates.TemplateResponse("detail.html", {
        "request": request,
        "title": APP_TITLE,
        "slug": slug,
        "conf": conf,
        "changelog": changelog,
        "commands": commands,
        "added": added == "1",
        "user": request.session.get("user", "admin"),
    })


@app.post("/client/{slug}/log")
async def add_log_entry(
    request: Request,
    slug: str,
    entry: str = Form(...),
    category: str = Form("general"),
):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)

    if not validate_slug(slug):
        raise HTTPException(status_code=400, detail="Slug inválido")

    # Validar y sanitizar entrada
    entry = entry.strip()[:1000]
    if not entry:
        raise HTTPException(status_code=400, detail="La entrada no puede estar vacía")

    valid_categories = {"deploy", "backup", "config", "support", "billing", "incidencia", "general"}
    if category not in valid_categories:
        category = "general"

    # Construir línea de log
    today = datetime.now().strftime("%Y-%m-%d")
    time_str = datetime.now().strftime("%H:%M")
    new_line = f"- **[{time_str}]** `{category.upper()}` {entry}\n"

    # Leer o inicializar changelog
    client_dir = CLIENTS_DIR / slug
    client_dir.mkdir(parents=True, exist_ok=True)
    changelog_path = client_dir / "CHANGELOG.md"

    if changelog_path.exists():
        content = changelog_path.read_text(encoding="utf-8")
    else:
        client_name = parse_conf(slug).get("CLIENT_NAME", slug)
        content = f"# Bitácora — {client_name}\n\n"

    # Insertar bajo sección del día (o crear sección nueva)
    date_header = f"## {today}"
    if date_header in content:
        content = content.replace(
            f"{date_header}\n",
            f"{date_header}\n{new_line}",
        )
    else:
        # Buscar primer "## " existente e insertar antes
        first_section = re.search(r"^## ", content, re.MULTILINE)
        new_section = f"{date_header}\n{new_line}\n"
        if first_section:
            pos = first_section.start()
            content = content[:pos] + new_section + content[pos:]
        else:
            content += "\n" + new_section

    changelog_path.write_text(content, encoding="utf-8")

    return RedirectResponse(f"/client/{slug}?added=1", status_code=302)


# ══════════════════════════════════════════════════════════════════════════════
# GESTIÓN DE TENANTS — tenants.json + provisionamiento via backend API
# ══════════════════════════════════════════════════════════════════════════════

def load_tenants() -> dict:
    """Lee tenants.json y retorna el dict (vacío si no existe o hay error)."""
    if not TENANTS_FILE.exists():
        return {}
    try:
        return json.loads(TENANTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_tenants(data: dict) -> None:
    """Escribe tenants.json con formato bonito."""
    TENANTS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


async def fetch_backend_stats() -> dict:
    """Llama al endpoint /api/v1/admin/stats del backend y retorna el payload."""
    if not ADMIN_API_SECRET:
        return {"tenants": {}, "stats": {}, "error": "ADMIN_API_SECRET no configurado"}
    try:
        async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=5.0) as client:
            resp = await client.get(
                "/api/v1/admin/stats",
                headers={"x-admin-token": ADMIN_API_SECRET},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        return {"tenants": {}, "stats": {}, "error": str(exc)}


async def backend_tenant_users(tenant_id: str) -> list:
    """Llama al endpoint /api/v1/admin/tenant-users/{tenant_id} del backend."""
    async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=8.0) as client:
        resp = await client.get(
            f"/api/v1/admin/tenant-users/{tenant_id}",
            headers={"x-admin-token": ADMIN_API_SECRET},
        )
        resp.raise_for_status()
        return resp.json()


async def backend_change_password(tenant_id: str, rut: str, new_password: str) -> dict:
    """Llama a POST /api/v1/admin/change-password en el backend."""
    async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=8.0) as client:
        resp = await client.post(
            "/api/v1/admin/change-password",
            headers={"x-admin-token": ADMIN_API_SECRET},
            json={"tenant_id": tenant_id, "rut": rut, "new_password": new_password},
        )
        resp.raise_for_status()
        return resp.json()


async def backend_provision(tenant_id: str, rut: str, email: str, full_name: str, password: str) -> dict:
    """Llama a POST /api/v1/admin/provision en el backend."""
    async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=10.0) as client:
        resp = await client.post(
            "/api/v1/admin/provision",
            headers={"x-admin-token": ADMIN_API_SECRET},
            json={
                "tenant_id": tenant_id,
                "rut": rut,
                "email": email,
                "full_name": full_name,
                "password": password,
            },
        )
        resp.raise_for_status()
        return resp.json()


# ── Rutas de tenants ──────────────────────────────────────────────────────────

@app.get("/tenants", response_class=HTMLResponse)
async def tenants_list(request: Request, msg: str = "", error: str = ""):
    if not is_authenticated(request):
        return RedirectResponse("/login?next=/tenants", status_code=302)

    # Leer tenants.json localmente
    tenants = load_tenants()

    # Intentar obtener estadísticas desde el backend
    backend_data = await fetch_backend_stats()
    stats = backend_data.get("stats", {})
    backend_error = backend_data.get("error", "")

    # Enriquecer lista de tenants con stats
    tenant_list = []
    for alias, info in tenants.items():
        s = stats.get(alias, {})
        tenant_list.append({
            "alias": alias,
            "name": info.get("name", alias),
            "active": info.get("active", True),
            "users": s.get("users", "—"),
            "tools": s.get("tools", "—"),
            "active_loans": s.get("active_loans", "—"),
        })

    # Ordenar: activos primero, luego alfabético
    tenant_list.sort(key=lambda t: (0 if t["active"] else 1, t["alias"]))

    return templates.TemplateResponse("tenants.html", {
        "request": request,
        "title": APP_TITLE,
        "user": request.session.get("user", "admin"),
        "tenant_list": tenant_list,
        "total": len(tenant_list),
        "active_count": sum(1 for t in tenant_list if t["active"]),
        "msg": msg,
        "error": error,
        "backend_error": backend_error,
        "now": datetime.now().strftime("%d/%m/%Y %H:%M"),
    })


@app.post("/tenants/new")
async def tenant_create(
    request: Request,
    alias: str = Form(...),
    name: str = Form(...),
    rut: str = Form(...),
    password: str = Form(...),
    email: str = Form(default=""),
    provision_user: str = Form(default="on"),
):
    """Crea un nuevo tenant en tenants.json y opcionalmente provisiona su admin."""
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)

    # Sanitizar alias
    alias = alias.strip().lower()
    if not re.match(r"^[a-z0-9][a-z0-9-]{0,49}$", alias):
        return RedirectResponse(
            "/tenants?error=Alias+inválido.+Usa+solo+minúsculas,+números+y+guiones.",
            status_code=302,
        )

    tenants = load_tenants()
    if alias in tenants:
        return RedirectResponse(
            f"/tenants?error=El+alias+'{alias}'+ya+existe.",
            status_code=302,
        )

    # 1. Agregar a tenants.json
    tenants[alias] = {"name": name.strip(), "active": True}
    save_tenants(tenants)

    # 2. Provisionar usuario admin en la BD si se solicitó
    provision_err = ""
    if provision_user == "on" and rut.strip():
        email_final = email.strip() or f"admin@{alias}.cl"
        try:
            await backend_provision(
                tenant_id=alias,
                rut=rut.strip(),
                email=email_final,
                full_name=f"Administrador {name.strip()}",
                password=password,
            )
        except httpx.HTTPStatusError as exc:
            body = exc.response.text
            provision_err = f"Tenant creado en tenants.json pero falló el provisionamiento de usuario: {body}"
        except Exception as exc:
            provision_err = f"Tenant creado en tenants.json pero falló el provisionamiento de usuario: {exc}"

    if provision_err:
        return RedirectResponse(
            f"/tenants?error={provision_err.replace(' ', '+')}",
            status_code=302,
        )

    return RedirectResponse(
        f"/tenants?msg=Tenant+'{alias}'+creado+correctamente.",
        status_code=302,
    )


@app.post("/tenants/{alias}/toggle")
async def tenant_toggle(request: Request, alias: str):
    """Activa o suspende un tenant en tenants.json."""
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)

    alias = alias.strip().lower()
    tenants = load_tenants()
    if alias not in tenants:
        return RedirectResponse("/tenants?error=Tenant+no+encontrado.", status_code=302)

    tenants[alias]["active"] = not tenants[alias].get("active", True)
    action = "activado" if tenants[alias]["active"] else "suspendido"
    save_tenants(tenants)

    return RedirectResponse(
        f"/tenants?msg=Tenant+'{alias}'+{action}+correctamente.",
        status_code=302,
    )


@app.post("/tenants/{alias}/add-user")
async def tenant_add_user(
    request: Request,
    alias: str,
    rut: str = Form(...),
    password: str = Form(...),
    email: str = Form(default=""),
    full_name: str = Form(default=""),
):
    """Provisiona un usuario adicional en un tenant existente."""
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)

    alias = alias.strip().lower()
    tenants = load_tenants()
    if alias not in tenants:
        return RedirectResponse("/tenants?error=Tenant+no+encontrado.", status_code=302)

    email_final = email.strip() or f"admin@{alias}.cl"
    name_final = full_name.strip() or f"Admin {alias}"

    try:
        await backend_provision(
            tenant_id=alias,
            rut=rut.strip(),
            email=email_final,
            full_name=name_final,
            password=password,
        )
    except httpx.HTTPStatusError as exc:
        err = exc.response.text.replace(" ", "+")
        return RedirectResponse(f"/tenants?error={err}", status_code=302)
    except Exception as exc:
        return RedirectResponse(f"/tenants?error={str(exc).replace(' ', '+')}", status_code=302)

    return RedirectResponse(
        f"/tenants?msg=Usuario+provisionado+en+'{alias}'+correctamente.",
        status_code=302,
    )


@app.get("/tenants/{alias}/users", response_class=HTMLResponse)
async def tenant_users_list(request: Request, alias: str, msg: str = "", error: str = ""):
    """Muestra los usuarios de un tenant y permite cambiar contraseñas."""
    if not is_authenticated(request):
        return RedirectResponse(f"/login?next=/tenants/{alias}/users", status_code=302)

    alias = alias.strip().lower()
    tenants = load_tenants()
    if alias not in tenants:
        return RedirectResponse("/tenants?error=Tenant+no+encontrado.", status_code=302)

    tenant_info = tenants[alias]
    users = []
    fetch_error = ""
    try:
        users = await backend_tenant_users(alias)
    except Exception as exc:
        fetch_error = str(exc)

    return templates.TemplateResponse("tenant_users.html", {
        "request": request,
        "title": APP_TITLE,
        "user": request.session.get("user", "admin"),
        "alias": alias,
        "tenant_name": tenant_info.get("name", alias),
        "users": users,
        "msg": msg,
        "error": error,
        "fetch_error": fetch_error,
    })


@app.post("/tenants/{alias}/users/{rut}/set-password")
async def tenant_set_password(
    request: Request,
    alias: str,
    rut: str,
    new_password: str = Form(...),
):
    """Cambia la contraseña de un usuario específico en un tenant."""
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)

    alias = alias.strip().lower()
    rut = rut.strip()

    if len(new_password) < 8:
        return RedirectResponse(
            f"/tenants/{alias}/users?error=La+contraseña+debe+tener+al+menos+8+caracteres.",
            status_code=302,
        )

    try:
        await backend_change_password(alias, rut, new_password)
    except httpx.HTTPStatusError as exc:
        err = exc.response.text.replace(" ", "+")[:200]
        return RedirectResponse(f"/tenants/{alias}/users?error={err}", status_code=302)
    except Exception as exc:
        return RedirectResponse(
            f"/tenants/{alias}/users?error={str(exc).replace(' ', '+')[:200]}",
            status_code=302,
        )

    return RedirectResponse(
        f"/tenants/{alias}/users?msg=Contraseña+actualizada+correctamente.",
        status_code=302,
    )
