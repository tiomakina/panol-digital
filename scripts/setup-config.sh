#!/usr/bin/env bash
# setup-config.sh — Crea los archivos de configuración fuera del repo
# Ejecutar una sola vez al provisionar el servidor.
# Uso: sudo bash scripts/setup-config.sh
set -euo pipefail

echo "════════════════════════════════════════"
echo "  Pañol 360 — Setup de configuración"
echo "════════════════════════════════════════"

# ── Directorios ────────────────────────────────────────────────────────────────
mkdir -p /etc/panol360/prod
mkdir -p /etc/panol360/staging

# ── tenants.json de PRODUCCIÓN ────────────────────────────────────────────────
if [[ -f /etc/panol360/prod/tenants.json ]]; then
  echo "→ /etc/panol360/prod/tenants.json ya existe — no se sobreescribe"
else
  # Si existe en el repo (primera migración), copiarlo; si no, crear uno vacío
  if [[ -f "$(dirname "$0")/../backend/app/tenants.json" ]]; then
    cp "$(dirname "$0")/../backend/app/tenants.json" /etc/panol360/prod/tenants.json
    echo "→ Copiado tenants.json actual → /etc/panol360/prod/tenants.json"
  else
    cat > /etc/panol360/prod/tenants.json <<'EOF'
{
  "demo": {
    "name": "Demo Empresa",
    "active": true,
    "env": "demo"
  }
}
EOF
    echo "→ Creado /etc/panol360/prod/tenants.json (plantilla vacía)"
  fi
fi

# ── tenants.json de STAGING ───────────────────────────────────────────────────
if [[ -f /etc/panol360/staging/tenants.json ]]; then
  echo "→ /etc/panol360/staging/tenants.json ya existe — no se sobreescribe"
else
  # Staging parte con los mismos tenants que prod pero con env=staging
  if [[ -f /etc/panol360/prod/tenants.json ]]; then
    # Reemplazar todos los valores de "env" por "staging"
    sed 's/"env": "[^"]*"/"env": "staging"/g' \
      /etc/panol360/prod/tenants.json > /etc/panol360/staging/tenants.json
    echo "→ Creado /etc/panol360/staging/tenants.json (env=staging para todos los tenants)"
  fi
fi

# ── releases.json — historial de versiones y changelogs ───────────────────────
if [[ -f /etc/panol360/releases.json ]]; then
  echo "→ /etc/panol360/releases.json ya existe — no se sobreescribe"
else
  cat > /etc/panol360/releases.json <<'EOF'
{
  "prod": { "commit": "unknown", "branch": "main", "deployed_at": null },
  "staging": { "commit": "unknown", "branch": "unknown", "deployed_at": null },
  "releases": []
}
EOF
  echo "→ Creado /etc/panol360/releases.json"
fi

# ── Permisos ──────────────────────────────────────────────────────────────────
chmod 640 /etc/panol360/prod/tenants.json
chmod 640 /etc/panol360/staging/tenants.json
chmod 664 /etc/panol360/releases.json

echo ""
echo "✓ Configuración lista:"
echo "  Prod:    /etc/panol360/prod/tenants.json"
echo "  Staging: /etc/panol360/staging/tenants.json"
echo "  Releases: /etc/panol360/releases.json"
echo ""
echo "Editar prod:    sudo nano /etc/panol360/prod/tenants.json"
echo "Editar staging: sudo nano /etc/panol360/staging/tenants.json"
