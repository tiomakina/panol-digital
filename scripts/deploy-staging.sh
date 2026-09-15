#!/usr/bin/env bash
# deploy-staging.sh — Despliega el código actual en el entorno de staging
# Asume que ya hiciste `git pull` antes de llamar este script.
# Uso: bash scripts/deploy-staging.sh
set -euo pipefail

COMPOSE="docker compose --profile staging"

echo "════════════════════════════════════════"
echo "  Pañol 360 — Deploy STAGING"
echo "  Commit: $(git rev-parse --short HEAD)"
echo "════════════════════════════════════════"

# 1. Crear la base de datos de staging si no existe
#    Se conecta a 'postgres' (base que siempre existe) para poder hacer CREATE DATABASE
echo "→ Verificando base de datos panol_staging..."
EXISTS=$(docker compose exec -T db psql -U panol -d postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname='panol_staging'")
if [[ "$EXISTS" != "1" ]]; then
  docker compose exec -T db psql -U panol -d postgres -c "CREATE DATABASE panol_staging;"
  echo "  ✓ panol_staging creada"
else
  echo "  ✓ panol_staging ya existe"
fi

# 2. Reconstruir imagen del backend (misma imagen que prod)
echo "→ Construyendo imagen..."
docker compose build backend

# 3. Levantar servicios de staging
echo "→ Levantando backend-staging y celery-staging-worker..."
$COMPOSE up -d --force-recreate backend-staging celery-staging-worker

echo ""
echo "✓ Staging en línea → https://staging.panol360.app"
echo "  Logs: docker compose --profile staging logs -f backend-staging"
