# syntax=docker/dockerfile:1
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATABASE_PATH=/data/manifest.sqlite3 COOKIE_SECURE=true
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home manifest && mkdir /data && chown manifest:manifest /data
COPY backend ./backend
COPY web ./web
RUN chmod -R a+rX /app/backend /app/web
USER manifest
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--preload", "--workers", "2", "--threads", "2", "--timeout", "120", "--access-logfile", "-", "backend.app:create_app()"]
