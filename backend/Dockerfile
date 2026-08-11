FROM python:3.12-slim

WORKDIR /app

# Dependencias de sistema para Pillow, WeasyPrint (PDFs) y compilación de paquetes Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p app/static/uploads/tools app/static/uploads/qr app/static/uploads/vouchers

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
