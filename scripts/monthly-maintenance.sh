#!/usr/bin/env bash
# monthly-maintenance.sh — Mantenimiento mensual automatizado panol360.app
#
# Uso (cron como usuario ubuntu):
#   CRON_TZ=America/Santiago
#   0 1 26 * * /home/ubuntu/panol-digital/scripts/monthly-maintenance.sh
#
# Requiere: .maintenance-email.conf con SMTP_USER y SMTP_PASS (ver ejemplo)
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOGDIR="$PROJECT_DIR/logs/maintenance"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOGFILE="$LOGDIR/$TIMESTAMP.log"
EMAIL_CONF="$PROJECT_DIR/scripts/.maintenance-email.conf"
EMAIL_SCRIPT="$PROJECT_DIR/scripts/send_maintenance_email.py"

mkdir -p "$LOGDIR"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOGFILE"; }

log "════════════════════════════════════════════"
log "  MANTENIMIENTO MENSUAL — panol360.app"
log "  Servidor: $(hostname) | $(date '+%d/%m/%Y %H:%M')"
log "════════════════════════════════════════════"
log ""

# ── 1. BACKUP ─────────────────────────────────────────────────────────────────
log "[ PASO 1 ] Backup del sistema"
cd "$PROJECT_DIR"
if bash scripts/backup.sh >> "$LOGFILE" 2>&1; then
    BACKUP_STATUS="Exitoso"
    BACKUP_OK=true
    log "✓ Backup completado"
else
    BACKUP_STATUS="FALLÓ — revisar logs"
    BACKUP_OK=false
    log "✗ Backup FALLÓ"
fi
log ""

# ── 2. ACTUALIZACIONES ────────────────────────────────────────────────────────
log "[ PASO 2 ] Actualizaciones del sistema"
sudo apt-get update -q >> "$LOGFILE" 2>&1
UPGRADABLE="$(apt list --upgradable 2>/dev/null | grep -vc '^Listing' || echo 0)"
log "  Paquetes con actualización disponible: $UPGRADABLE"

if sudo apt-get upgrade -y >> "$LOGFILE" 2>&1; then
    APT_STATUS="$UPGRADABLE paquetes actualizados"
    log "✓ apt upgrade completado"
else
    APT_STATUS="FALLÓ — revisar logs"
    log "✗ apt upgrade FALLÓ"
fi

sudo apt-get autoremove -y >> "$LOGFILE" 2>&1
sudo apt-get autoclean  >> "$LOGFILE" 2>&1
log "✓ Limpieza de paquetes completada"
log ""

# ── 3. CONTENEDORES DOCKER ────────────────────────────────────────────────────
log "[ PASO 3 ] Estado de contenedores Docker"
CONTAINERS_UP="$(docker compose ps --format '{{.Status}}' 2>/dev/null | grep -c 'Up' || echo 0)"
CONTAINERS_TOTAL="$(docker compose ps --format '{{.Name}}' 2>/dev/null | wc -l || echo 0)"
DOCKER_TABLE="$(docker compose ps --format 'table {{.Name}}\t{{.Status}}' 2>/dev/null || echo 'No se pudo obtener estado')"
echo "$DOCKER_TABLE" >> "$LOGFILE"
log "  Activos: $CONTAINERS_UP / $CONTAINERS_TOTAL"

# Limpieza de imágenes huérfanas
RECLAIMED="$(docker image prune -f 2>/dev/null | grep 'reclaimed' || echo 'sin imágenes huérfanas')"
log "  Limpieza Docker: $RECLAIMED"
log ""

# ── 4. DISCO ──────────────────────────────────────────────────────────────────
log "[ PASO 4 ] Espacio en disco"
DISK_LINE="$(df -h / | tail -1)"
DISK_USED="$(echo "$DISK_LINE" | awk '{print $3}')"
DISK_AVAIL="$(echo "$DISK_LINE" | awk '{print $4}')"
DISK_PCT="$(echo "$DISK_LINE" | awk '{print $5}')"
BACKUP_SIZE="$(du -sh "$PROJECT_DIR/backups/" 2>/dev/null | cut -f1 || echo '?')"
log "  Disco raíz: $DISK_USED usado ($DISK_PCT), $DISK_AVAIL disponible"
log "  Directorio backups: $BACKUP_SIZE"
log ""

# ── 5. KERNEL Y REBOOT ────────────────────────────────────────────────────────
KERNEL_VERSION="$(uname -r)"
REBOOT_NEEDED=""
if [ -f /var/run/reboot-required ]; then
    REBOOT_NEEDED="true"
    log "⚠️  ATENCIÓN: Se requiere reinicio del servidor (kernel nuevo instalado)"
else
    log "✓ No se requiere reinicio"
fi
log ""

# ── 6. PRÓXIMO MANTENIMIENTO ──────────────────────────────────────────────────
NEXT_DATE="$(date -d "$(date +%Y-%m-26) + 1 month" +"%d/%m/%Y" 2>/dev/null \
            || python3 -c "from datetime import date; d=date.today().replace(day=1); import calendar; m2=(d.month%12)+1; y2=d.year+(d.month//12); print(date(y2,m2,26).strftime('%d/%m/%Y'))")"

log "════════════════════════════════════════════"
log "  MANTENIMIENTO COMPLETADO"
log "  Próximo: $NEXT_DATE"
log "════════════════════════════════════════════"

# ── 7. EMAIL RESUMEN ──────────────────────────────────────────────────────────
if [ -f "$EMAIL_CONF" ] && [ -f "$EMAIL_SCRIPT" ]; then
    python3 "$EMAIL_SCRIPT" \
        --conf    "$EMAIL_CONF" \
        --backup  "$BACKUP_STATUS" \
        --apt     "$APT_STATUS" \
        --containers "$CONTAINERS_UP/$CONTAINERS_TOTAL" \
        --disk    "$DISK_PCT ($DISK_AVAIL libre)" \
        --kernel  "$KERNEL_VERSION" \
        --reboot  "$REBOOT_NEEDED" \
        --next    "$NEXT_DATE" \
        --logfile "$LOGFILE" \
        >> "$LOGFILE" 2>&1 \
    && log "✓ Email de resumen enviado" \
    || log "⚠️  Email no pudo enviarse (verificar .maintenance-email.conf)"
else
    log "⚠️  Email no configurado — ver scripts/.maintenance-email.conf.example"
fi
