FROM python:3.12-slim

# Metadata
LABEL maintainer="panol360"
LABEL description="Admin panel — acceso solo vía Tailscale VPN"

WORKDIR /app

# Dependencias del sistema mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código de la aplicación
COPY . .

# Usuario no-root por seguridad
RUN useradd -m -u 1001 adminpanel && chown -R adminpanel:adminpanel /app
USER adminpanel

EXPOSE 9001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:9001/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9001", "--no-access-log"]
