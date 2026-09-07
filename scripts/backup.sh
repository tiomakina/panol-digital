#!/usr/bin/env bash
# Backup de Pañol v2.0 — vuelca la base PostgreSQL y comprime los uploads
# (logos, fotos de herramientas, QR y vales PDF) en backups/<timestamp>/.
#
# Uso: bash scripts/backup.sh
# Requiere: los contenedores db (y opcionalmente backend) levantados via `make up`.
set -euo pipefail

cd "$(dirname "$0")/.."

# Carga segura de .env — NO usa `source` porque valores con caracteres
# especiales (ñ, tildes, guiones) rompen el shell con set -euo pipefail.
# Solo exporta líneas de la forma KEY=VALUE (saltar comentarios y vacías).
if [ -f .env ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    [[ "$line" =~ ^[[:space:]]*#  ]] && continue   # comentario
    [[ "$line" =~ ^[[:space:]]*$  ]] && continue   # línea vacía
    [[ "$line" =~ ^[a-zA-Z_][a-zA-Z0-9_]*= ]] || continue  # no es KEY=VALUE
    export "${line}" 2>/dev/null || true
  done < .env
fi

DB_USER="${DB_USER:-panol}"
DB_NAME="${DB_NAME:-panol_db}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="backups/${TIMESTAMP}"

mkdir -p "$BACKUP_DIR"

echo "📦 Generando backup en ${BACKUP_DIR}/ ..."

echo "  → Volcando base de datos PostgreSQL..."
if ! docker compose exec -T db pg_dump -U "$DB_USER" "$DB_NAME" > "${BACKUP_DIR}/database.sql" 2>/dev/null; then
  # Fallback para instalaciones con docker-compose v1 (guion)
  docker-compose exec -T db pg_dump -U "$DB_USER" "$DB_NAME" > "${BACKUP_DIR}/database.sql"
fi
echo "    ✓ database.sql ($(du -h "${BACKUP_DIR}/database.sql" | cut -f1))"

echo "  → Comprimiendo archivos subidos (logos, fotos, QR, vales)..."
if [ -d backend/app/static/uploads ]; then
  tar -czf "${BACKUP_DIR}/uploads.tar.gz" -C backend/app/static uploads
  echo "    ✓ uploads.tar.gz ($(du -h "${BACKUP_DIR}/uploads.tar.gz" | cut -f1))"
else
  echo "    ⚠ No se encontró backend/app/static/uploads, se omite"
fi

echo ""
echo "✅ Backup completo: ${BACKUP_DIR}/"
echo "   Para restaurar: bash scripts/restore.sh ${BACKUP_DIR}"
