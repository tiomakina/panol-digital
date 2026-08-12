#!/usr/bin/env bash
# Compila el instalador GUI (scripts/instalador_gui.py) con PyInstaller.
# Genera un ejecutable standalone en dist/: panol_setup(.exe) según el SO.
#
# Uso: bash scripts/build_installer.sh
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "❌ No se encontró Python 3. Instalalo antes de continuar."
  exit 1
fi

echo "🔧 Compilando instalador GUI de Pañol v2.0..."

if ! "$PYTHON" -m PyInstaller --version >/dev/null 2>&1; then
  echo "  → PyInstaller no está instalado, instalando..."
  "$PYTHON" -m pip install --quiet pyinstaller
fi

echo "  → Empaquetando scripts/instalador_gui.py (--onefile --windowed)..."
"$PYTHON" -m PyInstaller \
  --onefile \
  --windowed \
  --name panol_setup \
  --distpath dist \
  --workpath build \
  --specpath build \
  scripts/instalador_gui.py

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) OUTPUT="dist/panol_setup.exe" ;;
  *)                    OUTPUT="dist/panol_setup" ;;
esac

echo ""
if [ -f "$OUTPUT" ]; then
  echo "✅ Instalador generado: ${OUTPUT} ($(du -h "$OUTPUT" | cut -f1))"
else
  echo "⚠️  PyInstaller terminó pero no se encontró ${OUTPUT} — revisá la salida de arriba."
fi
