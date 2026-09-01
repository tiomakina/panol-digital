#!/bin/sh
# Entrypoint de la imagen del backend — usado por los 3 servicios que
# comparten esta imagen (backend, celery_worker, celery_beat), cada uno
# con su propio comando (ver docker-compose.yml).
#
# Las migraciones de Alembic se corren SOLO acá, y SOLO cuando el comando
# es el de Uvicorn (el servicio "backend"). Si las corriéramos también en
# celery_worker/celery_beat, dos contenedores intentarían aplicar el mismo
# ALTER/CREATE al mismo tiempo en el arranque — Alembic no serializa eso
# con un lock, así que directamente no lo intentamos ahí; esos servicios
# solo necesitan que el esquema YA esté aplicado, no aplicarlo ellos.
set -e

if [ "$1" = "uvicorn" ]; then
  echo "==> Aplicando migraciones de Alembic (alembic upgrade head)..."
  alembic upgrade head
fi

exec "$@"
