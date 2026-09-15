#!/usr/bin/env bash
# deploy-staging.sh — Despliega la rama actual en el entorno de staging
# Uso: bash scripts/deploy-staging.sh [rama]
# Si no se pasa rama, usa la rama actual del repositorio.
set -euo pipefail

BRANCH="${1:-$(git rev-parse --abbrev-ref HEAD)}"
COMPOSE="docker compose --profile staging"

echo "════════════════════════════════════════"
echo "  Pañol 360 — Deploy STAGING"
echo "  Rama: $BRANCH"
echo "════════════════════════════════════════"

# 1. Actualizar código
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

# 2. Crear la base de datos de staging si no existe
echo "→ Verificando base de datos panol_staging..."
docker compose exec -T db psql -U panol -tc \
  "SELECT 1 FROM pg_database WHERE datname='panol_staging'" | grep -q 1 || \
  docker compose exec -T db psql -U panol -c "CREATE DATABASE panol_staging;"
echo "  ✓ panol_staging lista"

# 3. Reconstruir imagen del backend (misma imagen que prod)
echo "→ Construyendo imagen..."
docker compose build backend

# 4. Levantar servicios de staging
echo "→ Levantando backend-staging y celery-staging-worker..."
$COMPOSE up -d --force-recreate backend-staging celery-staging-worker

echo ""
echo "✓ Staging en línea → https://staging.panol360.app"
echo "  Logs: docker compose --profile staging logs -f backend-staging"
