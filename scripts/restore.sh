#!/usr/bin/env bash
# Restaura un backup generado por scripts/backup.sh (base de datos + uploads).
#
# Uso: bash scripts/restore.sh backups/20260812_120000
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -z "${1:-}" ]; then
  echo "Uso: bash scripts/restore.sh <directorio_de_backup>"
  echo "Ejemplo: bash scripts/restore.sh backups/20260812_120000"
  exit 1
fi

BACKUP_DIR="$1"

if [ ! -d "$BACKUP_DIR" ]; then
  echo "❌ No existe el directorio: ${BACKUP_DIR}"
  exit 1
fi

# Carga segura de .env (sin source — ver comentario en backup.sh)
if [ -f .env ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    [[ "$line" =~ ^[[:space:]]*#  ]] && continue
    [[ "$line" =~ ^[[:space:]]*$  ]] && continue
    [[ "$line" =~ ^[a-zA-Z_][a-zA-Z0-9_]*= ]] || continue
    export "${line}" 2>/dev/null || true
  done < .env
fi

DB_USER="${DB_USER:-panol}"
DB_NAME="${DB_NAME:-panol_db}"

echo "⚠️  Esto va a SOBREESCRIBIR la base de datos '${DB_NAME}' y los archivos subidos actuales."
read -r -p "¿Continuar? [s/N] " confirm
if [[ ! "$confirm" =~ ^[sS]$ ]]; then
  echo "Cancelado."
  exit 0
fi

compose() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  else
    docker-compose "$@"
  fi
}

if [ -f "${BACKUP_DIR}/database.sql" ]; then
  echo "  → Restaurando base de datos desde database.sql..."
  compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 < "${BACKUP_DIR}/database.sql"
  echo "    ✓ Base de datos restaurada"
else
  echo "    ⚠ No se encontró ${BACKUP_DIR}/database.sql, se omite la base de datos"
fi

if [ -f "${BACKUP_DIR}/uploads.tar.gz" ]; then
  echo "  → Restaurando archivos subidos..."
  tar -xzf "${BACKUP_DIR}/uploads.tar.gz" -C backend/app/static
  echo "    ✓ Uploads restaurados"
else
  echo "    ⚠ No se encontró ${BACKUP_DIR}/uploads.tar.gz, se omite"
fi

echo ""
echo "✅ Restauración completa desde ${BACKUP_DIR}/"
echo "   Reiniciá el backend para que tome los cambios: make down && make up"
