# Imagen del backend: la API (FastAPI) y el bot (discord.py) comparten código; cambia solo el comando.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN useradd --create-home --uid 10001 nexus

COPY core/ core/
COPY api/ api/
COPY bot/ bot/
COPY migrations/ migrations/
COPY alembic.ini .

RUN pip install ./core ./api ./bot

USER nexus
# Por defecto la API; el bot usa "python -m nexus_bot" (ver docker-compose.yml).
CMD ["uvicorn", "nexus_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
