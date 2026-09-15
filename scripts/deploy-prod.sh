#!/usr/bin/env bash
# deploy-prod.sh — Despliega la rama principal en producción
# Uso: bash scripts/deploy-prod.sh
# Solo despliega desde 'main'. Si no estás en main, aborta.
set -euo pipefail

PROD_BRANCH="main"
CURRENT="$(git rev-parse --abbrev-ref HEAD)"

echo "════════════════════════════════════════"
echo "  Pañol 360 — Deploy PRODUCCIÓN"
echo "════════════════════════════════════════"

if [[ "$CURRENT" != "$PROD_BRANCH" ]]; then
  echo "✗ Error: estás en la rama '$CURRENT', no en '$PROD_BRANCH'."
  echo "  Fusiona tus cambios a main antes de desplegar a producción."
  exit 1
fi

# Confirmación explícita
read -rp "¿Desplegar a PRODUCCIÓN? Esto afecta a clientes reales. [s/N]: " CONFIRM
[[ "$CONFIRM" =~ ^[sS]$ ]] || { echo "Cancelado."; exit 0; }

# 1. Actualizar código
git fetch origin "$PROD_BRANCH"
git reset --hard "origin/$PROD_BRANCH"

# 2. Reconstruir imagen
echo "→ Construyendo imagen..."
docker compose build backend

# 3. Reiniciar servicios de producción (sin --profile: solo arranca los de prod)
echo "→ Reiniciando backend, celery_worker, celery_beat..."
docker compose up -d --force-recreate backend celery_worker celery_beat

echo ""
echo "✓ Producción actualizada → https://panol360.app"
echo "  Logs: docker compose logs -f backend"
