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

# Capturar info de git para inyectar en los contenedores
COMMIT=$(git rev-parse --short HEAD)
BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "main")
NOW=$(TZ=America/Santiago date +"%Y-%m-%dT%H:%M:%S")

export GIT_COMMIT="$COMMIT"
export GIT_BRANCH="$BRANCH"
export DEPLOYED_AT="$NOW"

echo "  Commit: $COMMIT  Branch: $BRANCH"
echo "  Fecha:  $NOW"

# 2. Reconstruir imagen
echo "→ Construyendo imagen..."
docker compose build backend

# 3. Reiniciar servicios de producción (sin --profile: solo arranca los de prod)
echo "→ Reiniciando backend, celery_worker, celery_beat..."
docker compose up -d --force-recreate backend celery_worker celery_beat

# 4. Actualizar registro en releases.json
RELEASES_FILE="/etc/panol360/releases.json"
if [[ -f "$RELEASES_FILE" ]]; then
  python3 - <<PYEOF
import json
try:
    with open("$RELEASES_FILE") as f:
        data = json.load(f)
except Exception:
    data = {"prod": {}, "staging": {}, "releases": []}

data["prod"] = {
    "commit": "$COMMIT",
    "branch": "$BRANCH",
    "deployed_at": "$NOW"
}

# Marcar el release correspondiente como deployed
for r in data.get("releases", []):
    if r.get("commit") == "$COMMIT":
        r["status"] = "deployed"
        r["promoted_at"] = "$NOW"

with open("$RELEASES_FILE", "w") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print("  ✓ releases.json actualizado")
PYEOF
fi

echo ""
echo "✓ Producción actualizada → https://panol360.app"
echo "  Logs: docker compose logs -f backend"
