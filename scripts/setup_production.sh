#!/usr/bin/env bash
# =============================================================================
# Pañol 360 — Setup de producción
# Ejecutar UNA VEZ en el servidor después del primer deploy.
#
# Qué hace:
#   1. Verifica/genera secrets seguros en .env
#   2. Configura renovación automática de SSL (certbot)
#   3. Configura backup diario automático (2:00 AM)
#   4. Configura limpieza de backups viejos (>7 días, 3:00 AM)
#
# Uso:  sudo bash scripts/setup_production.sh
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✅  $*${NC}"; }
warn() { echo -e "${YELLOW}⚠️   $*${NC}"; }
info() { echo -e "${BLUE}ℹ️   $*${NC}"; }
err()  { echo -e "${RED}❌  $*${NC}"; }

# Debe ejecutarse como root (necesario para crontab del sistema y certbot)
if [ "$(id -u)" -ne 0 ]; then
  err "Ejecutar como root: sudo bash scripts/setup_production.sh"
  exit 1
fi

# Directorio raíz del proyecto (el script está en scripts/)
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Pañol 360 — Setup de producción"
echo "  Directorio: $PROJECT_DIR"
echo "═══════════════════════════════════════════════════════"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# 1. SECRETS
# ─────────────────────────────────────────────────────────────────────────────
echo "── 1. Verificando secrets en .env ──"

ENV_FILE="$PROJECT_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
  warn ".env no existe — copiando desde .env.example"
  cp "$PROJECT_DIR/.env.example" "$ENV_FILE"
fi

generate_secret() {
  python3 -c "import secrets; print(secrets.token_hex(32))"
}

fix_secret() {
  local key="$1"
  local current
  current=$(grep "^${key}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo "")

  if [ -z "$current" ] || echo "$current" | grep -qi "cambiar\|CAMBIAR\|ejemplo\|example"; then
    local new_val
    new_val=$(generate_secret)
    if grep -q "^${key}=" "$ENV_FILE"; then
      sed -i "s|^${key}=.*|${key}=${new_val}|" "$ENV_FILE"
    else
      echo "${key}=${new_val}" >> "$ENV_FILE"
    fi
    ok "${key} generado → ${new_val:0:12}…"
  else
    ok "${key} ya está configurado"
  fi
}

fix_secret "SECRET_KEY"
fix_secret "JWT_SECRET_KEY"

echo ""

# ─────────────────────────────────────────────────────────────────────────────
# 2. CERTBOT AUTO-RENEWAL
# ─────────────────────────────────────────────────────────────────────────────
echo "── 2. Renovación automática de SSL (certbot) ──"

if ! command -v certbot &>/dev/null; then
  warn "certbot no encontrado — instalando..."
  apt-get install -y certbot > /dev/null 2>&1 || snap install --classic certbot > /dev/null 2>&1
fi

# El deploy-hook recarga nginx dentro del contenedor tras la renovación
CERTBOT_HOOK="cd ${PROJECT_DIR} && docker compose exec -T nginx nginx -s reload"
CERTBOT_CRON="0 3 * * * certbot renew --quiet --webroot --webroot-path /var/www/certbot --deploy-hook \"${CERTBOT_HOOK}\" >> /var/log/certbot-renew.log 2>&1"

if crontab -l 2>/dev/null | grep -q "certbot renew"; then
  ok "Cron de certbot ya existe"
else
  (crontab -l 2>/dev/null; echo "$CERTBOT_CRON") | crontab -
  ok "Cron de certbot configurado (diario a las 03:00)"
fi

# Prueba en seco para verificar que la renovación funciona
info "Verificando renovación en seco..."
if certbot renew --dry-run --webroot --webroot-path /var/www/certbot 2>&1 | grep -q "Congratulations\|no renewals\|not due\|would renew"; then
  ok "certbot --dry-run OK"
else
  certbot renew --dry-run --webroot --webroot-path /var/www/certbot 2>&1 | tail -5 || true
  warn "Revisar la salida de --dry-run arriba — puede que los paths difieran"
fi

echo ""

# ─────────────────────────────────────────────────────────────────────────────
# 3. BACKUP DIARIO
# ─────────────────────────────────────────────────────────────────────────────
echo "── 3. Backup automático diario ──"

BACKUP_CRON="0 2 * * * cd ${PROJECT_DIR} && bash scripts/backup.sh >> /var/log/panol-backup.log 2>&1"

if crontab -l 2>/dev/null | grep -q "panol.*backup\|backup.*panol"; then
  ok "Cron de backup ya existe"
else
  (crontab -l 2>/dev/null; echo "$BACKUP_CRON") | crontab -
  ok "Cron de backup configurado (diario a las 02:00)"
fi

echo ""

# ─────────────────────────────────────────────────────────────────────────────
# 4. LIMPIEZA DE BACKUPS VIEJOS (>7 días)
# ─────────────────────────────────────────────────────────────────────────────
echo "── 4. Limpieza de backups antiguos ──"

CLEANUP_CRON="0 4 * * * find ${PROJECT_DIR}/backups -maxdepth 1 -mindepth 1 -type d -mtime +7 -exec rm -rf {} + 2>/dev/null; true"

if crontab -l 2>/dev/null | grep -q "find.*backups.*mtime\|mtime.*backups"; then
  ok "Cron de limpieza ya existe"
else
  (crontab -l 2>/dev/null; echo "$CLEANUP_CRON") | crontab -
  ok "Cron de limpieza configurado (diario a las 04:00, borra >7 días)"
fi

echo ""

# ─────────────────────────────────────────────────────────────────────────────
# 5. RESUMEN
# ─────────────────────────────────────────────────────────────────────────────
echo "═══════════════════════════════════════════════════════"
echo "  Crontab actual:"
crontab -l 2>/dev/null | grep -v "^#\|^$" || echo "  (vacío)"
echo "═══════════════════════════════════════════════════════"
echo ""
echo -e "${GREEN}🎉  Setup de producción completado.${NC}"
echo ""
echo "  Próximos pasos:"
echo "  • Reiniciar el backend para aplicar los nuevos secrets:"
echo "    sudo docker compose up -d --no-deps backend"
echo ""
echo "  • Hacer un backup manual ahora para verificar:"
echo "    bash scripts/backup.sh"
echo ""
