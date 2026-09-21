FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AIDAR_DB=/data/aidar.db

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY patterns ./patterns
COPY web ./web
COPY scripts ./scripts

RUN pip install --no-cache-dir '.[web]'
RUN useradd --create-home --uid 10001 aidar \
    && mkdir -p /data \
    && chown -R aidar:aidar /app /data

USER aidar
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"

CMD ["uvicorn", "web.main:app", "--host", "0.0.0.0", "--port", "8000"]
