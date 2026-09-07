#!/bin/bash
# ══════════════════════════════════════════════════════════════════════════════
# Pañol 360 — Script de aprovisionamiento de nuevo tenant (cliente)
#
# Uso:
#   ./scripts/provision_tenant.sh <alias> "<Nombre Empresa>" <rut_admin> <pass_admin>
#
# Ejemplo:
#   ./scripts/provision_tenant.sh ferreteria-norte "Ferretería Norte Ltda." 12345678-9 Admin123!
#
# Lo que hace:
#   1. Valida que el alias no existe en tenants.json
#   2. Agrega el tenant a tenants.json
#   3. Dentro del contenedor backend crea el usuario administrador en la BD
#      con tenant_id = <alias>
#   4. Muestra un resumen del acceso para el cliente
#
# Requisitos:
#   - Ejecutar desde el directorio raíz del proyecto (donde está docker-compose.yml)
#   - El stack debe estar levantado (docker compose up -d)
# ══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── Argumentos ────────────────────────────────────────────────────────────────
ALIAS="${1:-}"
NOMBRE="${2:-}"
RUT_ADMIN="${3:-}"
PASS_ADMIN="${4:-}"

if [[ -z "$ALIAS" || -z "$NOMBRE" || -z "$RUT_ADMIN" || -z "$PASS_ADMIN" ]]; then
  echo "❌ Uso: $0 <alias> \"<Nombre Empresa>\" <rut_admin> <password>"
  echo "   Ejemplo: $0 ferreteria-norte \"Ferretería Norte Ltda.\" 12345678-9 Admin123!"
  exit 1
fi

# ── Validaciones ──────────────────────────────────────────────────────────────
TENANTS_FILE="backend/app/tenants.json"

if ! command -v jq &>/dev/null; then
  echo "❌ Se requiere 'jq'. Instálalo con: sudo apt-get install -y jq"
  exit 1
fi

if [[ ! -f "$TENANTS_FILE" ]]; then
  echo "❌ No se encontró $TENANTS_FILE. ¿Estás en el directorio raíz del proyecto?"
  exit 1
fi

# Verificar si el alias ya existe
EXISTE=$(jq -r --arg a "$ALIAS" 'has($a)' "$TENANTS_FILE")
if [[ "$EXISTE" == "true" ]]; then
  echo "❌ El alias '$ALIAS' ya existe en tenants.json. Elige otro."
  exit 1
fi

# Verificar que el stack esté levantado
if ! docker compose ps backend --status running --quiet 2>/dev/null | grep -q .; then
  echo "❌ El contenedor backend no está corriendo. Ejecuta: docker compose up -d"
  exit 1
fi

echo ""
echo "══════════════════════════════════════════════════"
echo "  Pañol 360 — Aprovisionando nuevo cliente"
echo "══════════════════════════════════════════════════"
echo "  Alias  : $ALIAS"
echo "  Empresa: $NOMBRE"
echo "  RUT    : $RUT_ADMIN"
echo "══════════════════════════════════════════════════"
echo ""

# ── Paso 1: Agregar tenant a tenants.json ─────────────────────────────────────
echo "📝 [1/3] Registrando tenant en tenants.json..."

TENANTS_ACTUALIZADO=$(jq --arg alias "$ALIAS" --arg nombre "$NOMBRE" \
  '. + {($alias): {"name": $nombre, "active": true}}' \
  "$TENANTS_FILE")

echo "$TENANTS_ACTUALIZADO" > "$TENANTS_FILE"
echo "     ✅ tenants.json actualizado"

# ── Paso 2: Copiar tenants.json actualizado al contenedor ─────────────────────
# (necesario si no hay volume mount — con el volume mount en docker-compose.yml
# ya es innecesario, pero lo hacemos de todos modos por seguridad)
echo "📦 [2/3] Sincronizando tenants.json con el contenedor..."
docker compose cp "$TENANTS_FILE" backend:/app/app/tenants.json
echo "     ✅ Copiado al contenedor"

# ── Paso 3: Crear usuario administrador en la base de datos ───────────────────
echo "👤 [3/3] Creando usuario administrador en la base de datos..."

# Script Python inline que se ejecuta dentro del contenedor backend
PYTHON_SCRIPT=$(cat <<'PYEOF'
import asyncio
import sys
import os

# El tenant y los datos vienen como argumentos de entorno
TENANT_ID  = os.environ["PROV_TENANT_ID"]
FULL_NAME  = os.environ.get("PROV_FULL_NAME", "Administrador")
RUT        = os.environ["PROV_RUT"]
EMAIL      = os.environ.get("PROV_EMAIL", f"admin@{TENANT_ID}.cl")
PASSWORD   = os.environ["PROV_PASSWORD"]

async def main():
    from app.core.database import AsyncSessionLocal
    from app.core.security import get_password_hash
    from app.core.rut import format_rut
    from app.models.user import User, UserRole
    from sqlalchemy import select

    try:
        rut_formateado = format_rut(RUT)
    except Exception:
        rut_formateado = RUT

    async with AsyncSessionLocal() as session:
        # Verificar si ya existe un admin con ese RUT en este tenant
        result = await session.execute(
            select(User).where(User.rut == rut_formateado, User.tenant_id == TENANT_ID)
        )
        existing = result.scalar_one_or_none()
        if existing:
            print(f"⚠️  Ya existe un usuario con RUT {rut_formateado} en tenant {TENANT_ID}")
            return

        admin = User(
            email=EMAIL,
            rut=rut_formateado,
            full_name=FULL_NAME,
            hashed_password=get_password_hash(PASSWORD),
            role=UserRole.jefe,
            is_active=True,
            tenant_id=TENANT_ID,
        )
        session.add(admin)
        await session.commit()
        print(f"✅ Usuario administrador creado: RUT={rut_formateado}, email={EMAIL}")

asyncio.run(main())
PYEOF
)

docker compose exec \
  -e PROV_TENANT_ID="$ALIAS" \
  -e PROV_FULL_NAME="Administrador $NOMBRE" \
  -e PROV_RUT="$RUT_ADMIN" \
  -e PROV_EMAIL="admin@${ALIAS}.cl" \
  -e PROV_PASSWORD="$PASS_ADMIN" \
  backend python -c "$PYTHON_SCRIPT"

# ── Resumen ───────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════"
echo "  ✅ Cliente aprovisionado correctamente"
echo "══════════════════════════════════════════════════"
echo ""
echo "  📋 Datos de acceso para el cliente:"
echo ""
echo "  URL     : https://panol360.app/"
echo "  Empresa : $ALIAS"
echo "  RUT     : $RUT_ADMIN"
echo "  Clave   : $PASS_ADMIN"
echo ""
echo "  ⚠️  Entregar esta información de forma segura al cliente."
echo "  ⚠️  El cliente debería cambiar la contraseña en su primer ingreso."
echo ""
echo "  📌 Para dar de baja este cliente en el futuro:"
echo "     jq '.\"$ALIAS\".active = false' backend/app/tenants.json > /tmp/t.json && mv /tmp/t.json backend/app/tenants.json"
echo "     docker compose cp backend/app/tenants.json backend:/app/app/tenants.json"
echo ""
