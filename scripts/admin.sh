#!/usr/bin/env bash
# =============================================================================
# admin.sh — Consola de Administración Pañol 360 SaaS
# =============================================================================
# Uso:
#   bash scripts/admin.sh <comando> [argumentos]
#
# Comandos disponibles:
#   list                       Listar todos los clientes y su estado
#   new                        Asistente para registrar un nuevo cliente
#   status  <slug>             Ver estado detallado de un cliente
#   update  <slug|all>         Actualizar deployment via SSH (git pull + rebuild)
#   log     <slug> "mensaje"   Agregar entrada a la bitácora del cliente
#   context <slug> [dev|prod]  Establecer contexto de sesión para Claude Code
#   open    <slug>             Abrir la URL del cliente en el navegador
#   ssh     <slug>             Conectarse por SSH al servidor del cliente
#   help                       Mostrar esta ayuda
# =============================================================================

set -euo pipefail

# ── Colores ─────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

# ── Rutas base ───────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLIENTS_DIR="$PROJECT_ROOT/clients"
SESSION_FILE="$PROJECT_ROOT/SESSION.md"
GLOBAL_CHANGELOG="$PROJECT_ROOT/CHANGELOG.md"

# ── Helpers ──────────────────────────────────────────────────────────────────
print_header() {
  echo ""
  echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}${CYAN}║      Pañol 360 — Admin Console           ║${NC}"
  echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════╝${NC}"
  echo ""
}

print_section() {
  echo -e "${BOLD}${BLUE}▶ $1${NC}"
}

print_ok() {
  echo -e "  ${GREEN}✓${NC} $1"
}

print_warn() {
  echo -e "  ${YELLOW}⚠${NC}  $1"
}

print_error() {
  echo -e "  ${RED}✗${NC} $1" >&2
}

require_slug() {
  local slug="$1"
  if [ -z "$slug" ]; then
    print_error "Falta el slug del cliente."
    echo "  Uso: $0 $2 <slug>"
    echo "  Clientes disponibles: $(list_slugs)"
    exit 1
  fi
  if [ ! -d "$CLIENTS_DIR/$slug" ]; then
    print_error "Cliente '$slug' no encontrado en $CLIENTS_DIR/"
    echo "  Clientes disponibles: $(list_slugs)"
    exit 1
  fi
}

list_slugs() {
  find "$CLIENTS_DIR" -maxdepth 1 -mindepth 1 -type d \
    ! -name '.*' -exec basename {} \; | sort | tr '\n' ' '
}

load_client_conf() {
  local slug="$1"
  local conf="$CLIENTS_DIR/$slug/client.conf"
  if [ ! -f "$conf" ]; then
    print_error "Archivo client.conf no encontrado para '$slug'"
    exit 1
  fi
  # Parseo seguro — no usamos source para evitar ejecución de código
  while IFS= read -r line || [ -n "$line" ]; do
    [[ "$line" =~ ^[[:space:]]*#  ]] && continue
    [[ "$line" =~ ^[[:space:]]*$  ]] && continue
    [[ "$line" =~ ^[a-zA-Z_][a-zA-Z0-9_]*= ]] || continue
    export "${line}" 2>/dev/null || true
  done < "$conf"
}

# ── Comando: list ─────────────────────────────────────────────────────────────
cmd_list() {
  print_header
  print_section "Clientes registrados"
  echo ""

  local total=0
  local activos=0

  if [ ! -d "$CLIENTS_DIR" ] || [ -z "$(ls -A "$CLIENTS_DIR" 2>/dev/null)" ]; then
    echo -e "  ${DIM}No hay clientes registrados aún.${NC}"
    echo ""
    echo "  Para crear uno: bash scripts/admin.sh new"
    return
  fi

  # Encabezado de tabla
  printf "  %-20s %-12s %-30s %-12s\n" "SLUG" "ESTADO" "DOMINIO" "PLAN"
  printf "  %-20s %-12s %-30s %-12s\n" "────────────────────" "────────────" "──────────────────────────────" "────────────"

  for client_dir in "$CLIENTS_DIR"/*/; do
    [ -d "$client_dir" ] || continue
    local slug
    slug=$(basename "$client_dir")
    [ "$slug" = "README.md" ] && continue

    total=$((total + 1))

    # Cargar variables del cliente en subshell para no contaminar el entorno
    local status company domain plan
    status=$(grep -m1 '^STATUS=' "$client_dir/client.conf" 2>/dev/null | cut -d= -f2- | tr -d '"' || echo "?")
    domain=$(grep -m1 '^DOMAIN=' "$client_dir/client.conf" 2>/dev/null | cut -d= -f2- | tr -d '"' || echo "?")
    plan=$(grep -m1 '^PLAN=' "$client_dir/client.conf" 2>/dev/null | cut -d= -f2- | tr -d '"' || echo "?")

    local status_color="$NC"
    case "$status" in
      active)     status_color="$GREEN"; activos=$((activos + 1)) ;;
      suspended)  status_color="$YELLOW" ;;
      cancelled)  status_color="$RED" ;;
    esac

    printf "  %-20s ${status_color}%-12s${NC} %-30s %-12s\n" "$slug" "$status" "$domain" "$plan"
  done

  echo ""
  echo -e "  ${DIM}Total: $total clientes — $activos activos${NC}"
  echo ""
}

# ── Comando: status ───────────────────────────────────────────────────────────
cmd_status() {
  local slug="${1:-}"
  require_slug "$slug" "status"

  print_header
  print_section "Estado del cliente: $slug"
  echo ""

  load_client_conf "$slug"

  echo -e "  ${BOLD}Empresa:${NC}        ${COMPANY_NAME:-?}"
  echo -e "  ${BOLD}Estado:${NC}         ${STATUS:-?}"
  echo -e "  ${BOLD}Servidor:${NC}       ${SERVER_USER:-ubuntu}@${SERVER_IP:-?}"
  echo -e "  ${BOLD}Directorio:${NC}     ${DEPLOY_PATH:-?}"
  echo -e "  ${BOLD}Dominio:${NC}        ${DOMAIN:-?}"
  echo -e "  ${BOLD}URL:${NC}            ${URL:-?}"
  echo -e "  ${BOLD}Plan:${NC}           ${PLAN:-?}"
  echo -e "  ${BOLD}Inicio:${NC}         ${CONTRACT_START:-?}"
  echo -e "  ${BOLD}Vencimiento:${NC}    ${CONTRACT_END:-(sin vencimiento)}"
  echo -e "  ${BOLD}Contacto:${NC}       ${CLIENT_NAME:-?} <${CLIENT_EMAIL:-?}>"

  if [ -n "${NOTES:-}" ]; then
    echo ""
    echo -e "  ${BOLD}Notas:${NC}          $NOTES"
  fi

  echo ""
  print_section "Últimas entradas de bitácora"
  echo ""

  local changelog="$CLIENTS_DIR/$slug/CHANGELOG.md"
  if [ -f "$changelog" ]; then
    # Mostrar las últimas 20 líneas significativas
    grep -E "^[-✅🔧⚠️🚨]|^## " "$changelog" | tail -15 | sed 's/^/  /'
  else
    echo "  (Sin entradas de bitácora)"
  fi

  echo ""

  # Intentar chequear si el sitio está up (si curl está disponible)
  if command -v curl &>/dev/null && [ -n "${URL:-}" ]; then
    print_section "Estado del sitio"
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${URL}/health" 2>/dev/null || echo "ERR")
    if [ "$http_code" = "200" ]; then
      print_ok "Sitio UP — /health respondió 200"
    else
      print_warn "Sitio responde: $http_code (o no accesible desde esta red)"
    fi
    echo ""
  fi
}

# ── Comando: new ──────────────────────────────────────────────────────────────
cmd_new() {
  print_header
  print_section "Registrar nuevo cliente"
  echo ""

  echo -e "  ${DIM}Asistente para crear el registro de un nuevo cliente.${NC}"
  echo -e "  ${DIM}Los datos se guardarán en clients/<slug>/client.conf${NC}"
  echo ""

  read -rp "  Slug (identificador único, ej: taller-vms): " slug
  slug=$(echo "$slug" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | sed 's/[^a-z0-9-]//g')

  if [ -z "$slug" ]; then
    print_error "El slug no puede estar vacío."
    exit 1
  fi

  if [ -d "$CLIENTS_DIR/$slug" ]; then
    print_error "Ya existe un cliente con slug '$slug'."
    exit 1
  fi

  read -rp "  Nombre de la empresa: " company_name
  read -rp "  IP del servidor: " server_ip
  read -rp "  Usuario SSH [ubuntu]: " server_user
  server_user="${server_user:-ubuntu}"
  read -rp "  Ruta de deploy en el servidor [/home/$server_user/panol-$slug]: " deploy_path
  deploy_path="${deploy_path:-/home/$server_user/panol-$slug}"
  read -rp "  Dominio (sin https://, ej: panol.empresa.cl): " domain
  read -rp "  Plan [demo/basico/profesional/enterprise]: " plan
  plan="${plan:-demo}"
  read -rp "  Fecha de inicio [$(date +%Y-%m-%d)]: " contract_start
  contract_start="${contract_start:-$(date +%Y-%m-%d)}"
  read -rp "  Nombre del contacto: " client_name
  read -rp "  Email del contacto: " client_email
  read -rp "  Teléfono del contacto: " client_phone
  read -rp "  Notas adicionales: " notes

  # Crear directorio
  mkdir -p "$CLIENTS_DIR/$slug"

  # Crear client.conf
  cat > "$CLIENTS_DIR/$slug/client.conf" << EOF
# ─────────────────────────────────────────────────────────────
# Cliente: $company_name
# ─────────────────────────────────────────────────────────────

SLUG=$slug
COMPANY_NAME="$company_name"
STATUS=active          # active | suspended | cancelled

# ── Servidor ──────────────────────────────────────────────────
SERVER_IP=$server_ip
SERVER_USER=$server_user
# SSH_KEY=~/.ssh/oracle_vms.key   # descomentar si usa clave propia
DEPLOY_PATH=$deploy_path

# ── Dominio y URL ─────────────────────────────────────────────
DOMAIN=$domain
URL=https://$domain

# ── Plan y facturación ────────────────────────────────────────
PLAN=$plan             # demo | basico | profesional | enterprise
BILLING_CONTACT=""
CONTRACT_START=$contract_start
CONTRACT_END=""        # vacío = sin fecha de vencimiento

# ── Contacto del cliente ──────────────────────────────────────
CLIENT_NAME="$client_name"
CLIENT_EMAIL="$client_email"
CLIENT_PHONE="$client_phone"

# ── Notas ─────────────────────────────────────────────────────
NOTES="$notes"
EOF

  # Crear CHANGELOG.md inicial
  cat > "$CLIENTS_DIR/$slug/CHANGELOG.md" << EOF
# Bitácora de Cambios — $company_name

> Registro cronológico de todos los cambios aplicados a este cliente.
> Agregar entradas con: \`bash scripts/admin.sh log $slug "descripción"\`

---

## $contract_start

### Registro inicial
- ✅ Cliente registrado en el sistema
- Plan: $plan
- Dominio: $domain

---
EOF

  echo ""
  print_ok "Cliente '$slug' registrado en $CLIENTS_DIR/$slug/"
  print_ok "Editá client.conf para agregar más detalles"
  echo ""
  echo -e "  ${BOLD}Próximos pasos:${NC}"
  echo "  1. Aprovisionar servidor con IP $server_ip"
  echo "  2. Clonar el repositorio en $deploy_path"
  echo "  3. Configurar .env en el servidor"
  echo "  4. bash scripts/admin.sh update $slug"
  echo "  5. bash scripts/admin.sh context $slug prod"
  echo ""
}

# ── Comando: update ───────────────────────────────────────────────────────────
cmd_update() {
  local target="${1:-}"

  if [ "$target" = "all" ]; then
    print_header
    print_section "Actualizar TODOS los clientes"
    echo ""
    for client_dir in "$CLIENTS_DIR"/*/; do
      [ -d "$client_dir" ] || continue
      local slug
      slug=$(basename "$client_dir")
      [ "$slug" = "README.md" ] && continue
      echo -e "  ${BOLD}→ $slug${NC}"
      _update_single "$slug" || true
      echo ""
    done
    return
  fi

  require_slug "$target" "update"
  print_header
  print_section "Actualizar cliente: $target"
  echo ""
  _update_single "$target"
}

_update_single() {
  local slug="$1"
  load_client_conf "$slug"

  local server="${SERVER_USER:-ubuntu}@${SERVER_IP:-}"
  local path="${DEPLOY_PATH:-}"
  local ssh_key="${SSH_KEY:-}"

  if [ -z "${SERVER_IP:-}" ]; then
    print_error "SERVER_IP no configurado en client.conf de '$slug'"
    return 1
  fi

  local ssh_opts="-o StrictHostKeyChecking=no -o ConnectTimeout=15"
  if [ -n "$ssh_key" ]; then
    ssh_opts="$ssh_opts -i $ssh_key"
  fi

  echo -e "  ${DIM}Conectando a $server...${NC}"

  local remote_cmd="
    set -e
    cd '$path' || { echo 'ERROR: No se puede entrar al directorio $path'; exit 1; }
    echo '→ git pull origin main...'
    git pull origin main
    echo '→ Reconstruyendo backend...'
    sudo docker compose up -d --build backend
    echo '→ Verificando estado...'
    sudo docker compose ps
    echo '✓ Actualización completada'
  "

  # shellcheck disable=SC2086
  if ssh $ssh_opts "$server" "$remote_cmd"; then
    print_ok "Actualización exitosa para '$slug'"
    # Agregar entrada a la bitácora
    _append_log "$slug" "🔄 Actualización desplegada (git pull + docker rebuild)"
  else
    print_error "Falló la actualización de '$slug'"
    return 1
  fi
}

# ── Comando: log ──────────────────────────────────────────────────────────────
cmd_log() {
  local slug="${1:-}"
  local message="${2:-}"

  require_slug "$slug" "log"

  if [ -z "$message" ]; then
    print_error "Falta el mensaje."
    echo "  Uso: $0 log <slug> \"descripción del cambio\""
    exit 1
  fi

  _append_log "$slug" "$message"
  print_ok "Entrada agregada a la bitácora de '$slug'"
}

_append_log() {
  local slug="$1"
  local message="$2"
  local changelog="$CLIENTS_DIR/$slug/CHANGELOG.md"
  local today
  today=$(date '+%Y-%m-%d %H:%M')

  # Si el CHANGELOG no existe, crearlo
  if [ ! -f "$changelog" ]; then
    echo "# Bitácora de Cambios — $slug" > "$changelog"
    echo "" >> "$changelog"
  fi

  # Verificar si ya existe la sección de hoy
  local today_date
  today_date=$(date '+%Y-%m-%d')
  if ! grep -q "^## $today_date" "$changelog" 2>/dev/null; then
    echo "" >> "$changelog"
    echo "---" >> "$changelog"
    echo "" >> "$changelog"
    echo "## $today_date" >> "$changelog"
    echo "" >> "$changelog"
  fi

  echo "- [$today] $message" >> "$changelog"
}

# ── Comando: context ──────────────────────────────────────────────────────────
cmd_context() {
  local slug="${1:-}"
  local env="${2:-prod}"

  if [ "$slug" = "sistema" ] || [ "$slug" = "system" ]; then
    # Contexto global (sin cliente específico)
    _write_session_system "$env"
    return
  fi

  require_slug "$slug" "context"
  load_client_conf "$slug"

  _write_session_client "$slug" "$env"
}

_write_session_client() {
  local slug="$1"
  local env="$2"
  local timestamp
  timestamp=$(date '+%Y-%m-%d %H:%M')

  cat > "$SESSION_FILE" << EOF
# SESSION.md — Contexto de sesión activa
> Generado automáticamente por \`admin.sh context\`. No editar manualmente.
> Claude Code lee este archivo al inicio de cada sesión.

---

## ¿En qué estamos trabajando?

| Campo | Valor |
|-------|-------|
| **Cliente** | ${COMPANY_NAME:-$slug} |
| **Slug** | $slug |
| **Entorno** | $env |
| **Servidor** | ${SERVER_USER:-ubuntu}@${SERVER_IP:-?} |
| **Directorio** | ${DEPLOY_PATH:-?} |
| **URL** | ${URL:-?} |
| **Sesión iniciada** | $timestamp |

---

## Instrucciones para Claude

- Todos los cambios de código que hagas aplican al sistema base (repo \`panol-digital\`)
- El cliente activo es **${COMPANY_NAME:-$slug}** (slug: \`$slug\`)
- Entorno: **$env**
$(if [ "$env" = "prod" ]; then
echo "- ⚠️  Estamos en PRODUCCIÓN — tener cuidado con cambios que requieran downtime"
echo "- Los cambios se aplican en: ${DEPLOY_PATH:-?}"
else
echo "- Estamos en DESARROLLO — podemos probar libremente"
fi)

## Para aplicar cambios en el servidor

\`\`\`bash
# 1. Commit y push (Claude lo hace)
git add . && git commit -m "feat: descripción" && git push

# 2. En el servidor (vos lo hacés):
ssh ${SERVER_USER:-ubuntu}@${SERVER_IP:-?}
cd ${DEPLOY_PATH:-~/panol-digital}
git pull origin main
sudo docker compose up -d --build backend
\`\`\`

## Bitácora del cliente

Ver: \`clients/$slug/CHANGELOG.md\`

---

*Para cambiar de contexto: \`bash scripts/admin.sh context <slug> [dev|prod]\`*
EOF

  echo ""
  print_ok "Contexto establecido: $slug ($env)"
  echo ""
  echo -e "  ${DIM}SESSION.md actualizado. Claude Code lo leerá en la próxima sesión.${NC}"
  echo ""
  echo -e "  ${BOLD}Recordatorio:${NC} Ahora podés abrir Claude Code y decirle:"
  echo -e "  ${DIM}\"Estamos trabajando en VMS Ingeniería en producción. Ver SESSION.md.\"${NC}"
  echo ""
}

_write_session_system() {
  local env="$1"
  local timestamp
  timestamp=$(date '+%Y-%m-%d %H:%M')

  cat > "$SESSION_FILE" << EOF
# SESSION.md — Contexto de sesión activa
> Generado automáticamente por \`admin.sh context\`. No editar manualmente.
> Claude Code lee este archivo al inicio de cada sesión.

---

## ¿En qué estamos trabajando?

| Campo | Valor |
|-------|-------|
| **Contexto** | Sistema base (sin cliente específico) |
| **Entorno** | $env |
| **Sesión iniciada** | $timestamp |

---

## Instrucciones para Claude

- Estamos trabajando en el **sistema base** — cambios que afectan a TODOS los clientes
- Entorno: **$env**
- Los cambios se harán en el repositorio \`panol-digital\` en la rama de desarrollo

---

*Para cambiar de contexto: \`bash scripts/admin.sh context <slug> [dev|prod]\`*
EOF

  echo ""
  print_ok "Contexto establecido: sistema ($env)"
  echo -e "  ${DIM}SESSION.md actualizado.${NC}"
  echo ""
}

# ── Comando: open ─────────────────────────────────────────────────────────────
cmd_open() {
  local slug="${1:-}"
  require_slug "$slug" "open"
  load_client_conf "$slug"

  local url="${URL:-}"
  if [ -z "$url" ]; then
    print_error "URL no configurada en client.conf de '$slug'"
    exit 1
  fi

  echo ""
  echo -e "  ${BOLD}Abriendo:${NC} $url"
  echo ""

  if command -v xdg-open &>/dev/null; then
    xdg-open "$url"
  elif command -v open &>/dev/null; then
    open "$url"
  else
    echo "  No se puede abrir automáticamente. Abrí esta URL en tu navegador:"
    echo "  $url"
  fi
}

# ── Comando: ssh ──────────────────────────────────────────────────────────────
cmd_ssh() {
  local slug="${1:-}"
  require_slug "$slug" "ssh"
  load_client_conf "$slug"

  local server="${SERVER_USER:-ubuntu}@${SERVER_IP:-}"
  local ssh_key="${SSH_KEY:-}"

  if [ -z "${SERVER_IP:-}" ]; then
    print_error "SERVER_IP no configurado en client.conf de '$slug'"
    exit 1
  fi

  echo ""
  echo -e "  ${BOLD}Conectando a:${NC} $server"
  echo ""

  local ssh_opts="-o StrictHostKeyChecking=no"
  if [ -n "$ssh_key" ]; then
    ssh_opts="$ssh_opts -i $ssh_key"
  fi

  # shellcheck disable=SC2086
  ssh $ssh_opts "$server"
}

# ── Comando: help ─────────────────────────────────────────────────────────────
cmd_help() {
  print_header
  echo -e "  ${BOLD}USO:${NC}"
  echo "    bash scripts/admin.sh <comando> [argumentos]"
  echo ""
  echo -e "  ${BOLD}COMANDOS:${NC}"
  echo ""
  printf "    ${GREEN}%-30s${NC} %s\n" "list" "Listar todos los clientes y su estado"
  printf "    ${GREEN}%-30s${NC} %s\n" "new" "Asistente para registrar un nuevo cliente"
  printf "    ${GREEN}%-30s${NC} %s\n" "status <slug>" "Ver estado detallado de un cliente"
  printf "    ${GREEN}%-30s${NC} %s\n" "update <slug|all>" "Actualizar deployment via SSH"
  printf "    ${GREEN}%-30s${NC} %s\n" "log <slug> \"mensaje\"" "Agregar entrada a la bitácora"
  printf "    ${GREEN}%-30s${NC} %s\n" "context <slug> [dev|prod]" "Establecer contexto para Claude Code"
  printf "    ${GREEN}%-30s${NC} %s\n" "context sistema [dev|prod]" "Contexto del sistema base"
  printf "    ${GREEN}%-30s${NC} %s\n" "open <slug>" "Abrir URL del cliente en el navegador"
  printf "    ${GREEN}%-30s${NC} %s\n" "ssh <slug>" "Conectarse por SSH al servidor"
  printf "    ${GREEN}%-30s${NC} %s\n" "help" "Mostrar esta ayuda"
  echo ""
  echo -e "  ${BOLD}EJEMPLOS:${NC}"
  echo ""
  echo "    bash scripts/admin.sh list"
  echo "    bash scripts/admin.sh status vms-ingenieria"
  echo "    bash scripts/admin.sh log vms-ingenieria \"Actualicé el logo\""
  echo "    bash scripts/admin.sh context vms-ingenieria prod"
  echo "    bash scripts/admin.sh update vms-ingenieria"
  echo "    bash scripts/admin.sh update all"
  echo ""
  echo -e "  ${BOLD}SLUGS DISPONIBLES:${NC}"
  echo ""
  echo "    $(list_slugs || echo '(ninguno)')"
  echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
  local cmd="${1:-help}"
  shift || true

  case "$cmd" in
    list)         cmd_list ;;
    new)          cmd_new ;;
    status)       cmd_status "$@" ;;
    update)       cmd_update "$@" ;;
    log)          cmd_log "$@" ;;
    context)      cmd_context "$@" ;;
    open)         cmd_open "$@" ;;
    ssh)          cmd_ssh "$@" ;;
    help|--help|-h) cmd_help ;;
    *)
      print_error "Comando desconocido: '$cmd'"
      echo "  Corré: bash scripts/admin.sh help"
      exit 1
      ;;
  esac
}

main "$@"
