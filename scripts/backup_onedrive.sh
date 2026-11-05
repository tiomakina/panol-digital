#!/usr/bin/env bash
# Backup Pañol 360 → OneDrive
# Vuelca BD + uploads + config, comprime y sube a OneDrive:/respaldo panol360/YYYY-MM-DD/
# Retiene los últimos 30 días; borra entradas más antiguas del OneDrive.
#
# Uso:   bash scripts/backup_onedrive.sh
# Cron:  0 3 * * * /home/ubuntu/panol-digital/scripts/backup_onedrive.sh >> /var/log/panol360-backup.log 2>&1
set -euo pipefail

PROYECTO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FECHA="$(date +%Y-%m-%d)"
HORA="$(date +%H%M%S)"
TIMESTAMP="${FECHA}_${HORA}"
BACKUP_LOCAL="/tmp/panol360_backup_${TIMESTAMP}"
ONEDRIVE_BASE="respaldo panol360"
ONEDRIVE_DESTINO="${ONEDRIVE_BASE}/${FECHA}"
RETENER_DIAS=30
LOG_TAG="[panol360-backup ${TIMESTAMP}]"

cd "$PROYECTO_DIR"

echo ""
echo "════════════════════════════════════════════════════════"
echo "${LOG_TAG} Iniciando backup"
echo "════════════════════════════════════════════════════════"

mkdir -p "$BACKUP_LOCAL"

# ── 1. Base de datos PostgreSQL (prod) ───────────────────────────────────────
echo "${LOG_TAG} Volcando BD panol_db (prod)..."
if docker compose exec -T db pg_dump -U panol panol_db > "${BACKUP_LOCAL}/panol_db.sql" 2>/dev/null; then
  echo "${LOG_TAG}   ✓ panol_db.sql ($(du -h "${BACKUP_LOCAL}/panol_db.sql" | cut -f1))"
else
  echo "${LOG_TAG}   ✗ ERROR al volcar panol_db — abortando"
  rm -rf "$BACKUP_LOCAL"
  exit 1
fi

# ── 2. Base de datos PostgreSQL (staging) ────────────────────────────────────
echo "${LOG_TAG} Volcando BD panol_staging..."
if docker compose exec -T db pg_dump -U panol panol_staging > "${BACKUP_LOCAL}/panol_staging.sql" 2>/dev/null; then
  echo "${LOG_TAG}   ✓ panol_staging.sql ($(du -h "${BACKUP_LOCAL}/panol_staging.sql" | cut -f1))"
else
  echo "${LOG_TAG}   ⚠ panol_staging no existe o no es accesible — se omite"
  rm -f "${BACKUP_LOCAL}/panol_staging.sql"
fi

# ── 3. Uploads (logos, fotos, QR, vales PDF) ─────────────────────────────────
echo "${LOG_TAG} Comprimiendo uploads..."
if [ -d backend/app/static/uploads ]; then
  tar -czf "${BACKUP_LOCAL}/uploads.tar.gz" -C backend/app/static uploads
  echo "${LOG_TAG}   ✓ uploads.tar.gz ($(du -h "${BACKUP_LOCAL}/uploads.tar.gz" | cut -f1))"
else
  echo "${LOG_TAG}   ⚠ No se encontró uploads/ — se omite"
fi

# ── 4. Configuración del sistema (/etc/panol360/) ────────────────────────────
echo "${LOG_TAG} Respaldando /etc/panol360/ (tenants.json, .env)..."
if [ -d /etc/panol360 ]; then
  tar -czf "${BACKUP_LOCAL}/config_etc.tar.gz" /etc/panol360/ 2>/dev/null
  echo "${LOG_TAG}   ✓ config_etc.tar.gz ($(du -h "${BACKUP_LOCAL}/config_etc.tar.gz" | cut -f1))"
else
  echo "${LOG_TAG}   ⚠ /etc/panol360/ no encontrado — se omite"
fi

# ── 5. .env del proyecto ──────────────────────────────────────────────────────
if [ -f .env ]; then
  cp .env "${BACKUP_LOCAL}/panol360.env"
  echo "${LOG_TAG}   ✓ panol360.env"
fi

# ── 6. Comprimir todo en un .tar.gz final ────────────────────────────────────
ARCHIVO_FINAL="/tmp/panol360_${TIMESTAMP}.tar.gz"
echo "${LOG_TAG} Comprimiendo paquete final..."
tar -czf "$ARCHIVO_FINAL" -C /tmp "panol360_backup_${TIMESTAMP}"
rm -rf "$BACKUP_LOCAL"
echo "${LOG_TAG}   ✓ $(basename "$ARCHIVO_FINAL") ($(du -h "$ARCHIVO_FINAL" | cut -f1))"

# ── 7. Subir a OneDrive ───────────────────────────────────────────────────────
echo "${LOG_TAG} Subiendo a OneDrive: '${ONEDRIVE_DESTINO}/'..."
if rclone copy "$ARCHIVO_FINAL" "onedrive:${ONEDRIVE_DESTINO}/" --progress 2>/dev/null; then
  echo "${LOG_TAG}   ✓ Subido correctamente"
else
  echo "${LOG_TAG}   ✗ ERROR al subir a OneDrive"
  rm -f "$ARCHIVO_FINAL"
  exit 1
fi

rm -f "$ARCHIVO_FINAL"

# ── 8. Limpiar backups con más de RETENER_DIAS días ──────────────────────────
echo "${LOG_TAG} Limpiando backups con más de ${RETENER_DIAS} días en OneDrive..."
FECHA_LIMITE="$(date -d "-${RETENER_DIAS} days" +%Y-%m-%d)"
rclone lsf "onedrive:${ONEDRIVE_BASE}/" --dirs-only 2>/dev/null | while read -r carpeta; do
  nombre="${carpeta%/}"
  # Solo procesa carpetas con formato YYYY-MM-DD
  if [[ "$nombre" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    if [[ "$nombre" < "$FECHA_LIMITE" ]]; then
      echo "${LOG_TAG}   🗑  Eliminando backup antiguo: ${nombre}"
      rclone purge "onedrive:${ONEDRIVE_BASE}/${nombre}" 2>/dev/null || true
    fi
  fi
done

echo "${LOG_TAG} ✅ Backup completado exitosamente"
echo "════════════════════════════════════════════════════════"
