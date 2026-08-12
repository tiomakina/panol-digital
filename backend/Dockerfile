# Se fija "-bookworm" en vez del tag flotante "slim": Debian upstream ya
# rotó "slim" de bookworm a trixie, y los nombres de paquetes apt cambian
# entre versiones — sin este pin, el build se rompe cada vez que Debian
# avanza su release "stable" por debajo nuestro.
FROM python:3.12-slim-bookworm

WORKDIR /app

# Dependencias de sistema para compilar paquetes Python nativos (bcrypt,
# asyncpg). No se instalan libpango/libcairo/libgdk-pixbuf: esas son para
# WeasyPrint, que no se usa — los vales PDF se generan con reportlab, que
# es Python puro y no necesita librerías nativas de renderizado.
# postgresql-client trae pg_dump/psql, que usa el módulo de respaldo
# integral (app/services/backup_service.py) para generar y restaurar
# backups directo desde la web, sin pasar por `docker compose exec`.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev libffi-dev postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p app/static/uploads/tools app/static/uploads/qr app/static/uploads/vouchers

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
