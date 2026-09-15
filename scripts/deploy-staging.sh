#!/usr/bin/env bash
# deploy-staging.sh — Despliega el código actual en el entorno de staging
# Asume que ya hiciste `git pull` antes de llamar este script.
# Uso: bash scripts/deploy-staging.sh
set -euo pipefail

COMPOSE="docker compose --profile staging"
COMMIT=$(git rev-parse --short HEAD)
BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "detached")
NOW=$(date -u +"%Y-%m-%dT%H:%M:%S")
RELEASE_ID="${NOW:0:10}-${COMMIT}"
RELEASES_FILE="/etc/panol360/releases.json"

# Exportar vars para que docker-compose las inyecte en el contenedor
export GIT_COMMIT="$COMMIT"
export GIT_BRANCH="$BRANCH"
export DEPLOYED_AT="$NOW"

echo "════════════════════════════════════════"
echo "  Pañol 360 — Deploy STAGING"
echo "  Commit: $COMMIT  Branch: $BRANCH"
echo "  Fecha:  $NOW"
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

# 4. Registrar deploy en releases.json
echo "→ Registrando release en releases.json..."
if [[ -f "$RELEASES_FILE" ]]; then
  python3 - <<PYEOF
import json, sys
try:
    with open("$RELEASES_FILE") as f:
        data = json.load(f)
except Exception:
    data = {"prod": {}, "staging": {}, "releases": []}

new_release = {
    "id": "$RELEASE_ID",
    "commit": "$COMMIT",
    "branch": "$BRANCH",
    "deployed_at": "$NOW",
    "environment": "staging",
    "status": "pending",
    "approved_at": None,
    "approved_by": None,
    "promoted_at": None,
    "changelog": []
}

# Evitar duplicados por commit
data["releases"] = [r for r in data.get("releases", []) if r.get("commit") != "$COMMIT"]
data["releases"].insert(0, new_release)
# Guardar solo los últimos 20 releases
data["releases"] = data["releases"][:20]
data["staging"] = {
    "commit": "$COMMIT",
    "branch": "$BRANCH",
    "deployed_at": "$NOW",
    "release_id": "$RELEASE_ID"
}
with open("$RELEASES_FILE", "w") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print("  ✓ Release $RELEASE_ID registrado")
PYEOF
else
  echo "  ⚠ $RELEASES_FILE no existe — ejecutar setup-config.sh primero"
fi

echo ""
echo "✓ Staging en línea → https://staging.panol360.app"
echo "  Logs: docker compose --profile staging logs -f backend-staging"
