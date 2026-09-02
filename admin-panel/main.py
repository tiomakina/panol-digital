#!/usr/bin/env python3
"""
Pañol 360 — Admin Panel
Panel de administración de clientes SaaS.
Acceso exclusivamente vía Tailscale VPN.
"""
import os
import re
import bcrypt
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

# ─── Configuración ────────────────────────────────────────────────────────────
CLIENTS_DIR = Path(os.environ.get("CLIENTS_DIR", "/app/clients"))
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
