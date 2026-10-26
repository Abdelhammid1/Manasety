FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 app

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN mkdir -p /app/instance /app/media && chown -R app:app /app
USER app

EXPOSE 8000
# Migrations run on start so a new image never serves an old schema.
CMD ["sh", "-c", "flask --app wsgi db upgrade -d migrations && gunicorn -w 3 -b 0.0.0.0:8000 --access-logfile - --forwarded-allow-ips='*' wsgi:app"]
HEALTHCHECK --interval=30s --timeout=5s CMD curl -fs http://127.0.0.1:8000/robots.txt || exit 1
