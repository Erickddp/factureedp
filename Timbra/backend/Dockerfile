# Timbra en un servidor (Railway, Render, Fly.io…). Sirve la API y también las pantallas (carpeta static).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    ENTORNO=web DATA_DIR=/data DATABASE_URL=sqlite:////data/timbra.db TZ=America/Mexico_City

# Chromium genera los PDF igual que Edge/Chrome en Windows; las fuentes evitan cuadritos en lugar de letras.
RUN apt-get update && apt-get install -y --no-install-recommends chromium fonts-liberation fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY alembic.ini ./
COPY migraciones ./migraciones
COPY app ./app
COPY static ./static

# /data debe ser un disco persistente: ahí viven la base de datos, los XML timbrados y la configuración.
# En Railway se crea desde el panel (Volume montado en /data): Railway NO acepta la instrucción VOLUME en el Dockerfile.
# Con Docker a secas: docker run -v timbra_datos:/data ...
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
