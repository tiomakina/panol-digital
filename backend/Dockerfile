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
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# postgresql-client (pg_dump/psql, para el módulo de respaldo integral —
# app/services/backup_service.py — que genera y restaura backups directo
# desde la web sin pasar por `docker compose exec`) tiene que ser la MISMA
# versión mayor que el server de docker-compose.yml (postgres:16-alpine).
# El paquete "postgresql-client" genérico de los repos de Debian bookworm
# resuelve a la v15 (la versión "stable" de Debian en este momento), no a
# la 16 — y pg_dump se niega a hablar con un server más nuevo que él mismo
# ("aborting because of server version mismatch"). Por eso se agrega el
# repo oficial de PGDG y se pide postgresql-client-16 explícito, en vez de
# depender de lo que Debian traiga por defecto.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates gnupg lsb-release curl \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] http://apt.postgresql.org/pub/repos/apt/ $(lsb_release -cs)-pgdg main" \
       > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends postgresql-client-16 \
    && apt-get purge -y gnupg lsb-release curl && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p app/static/uploads/tools app/static/uploads/qr app/static/uploads/vouchers
# sed -i 's/\r$//' por las dudas: si este proyecto se clona en Windows sin
# el .gitattributes aplicado (checkout viejo, o simplemente porque git lo
# convirtió a CRLF), el shebang de docker-entrypoint.sh queda roto dentro
# del contenedor Linux y el backend entra en bucle de reinicio. Con esto
# el build deja el script sano sin importar de qué SO vino el checkout.
RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
