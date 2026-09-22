# ── Build target: Raspberry Pi 4/5 (linux/arm64) ──────────────────────────────
# Build: docker buildx build --platform linux/arm64 -t iot208-service .
# Run:   docker compose up -d
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim-bookworm

# ── System deps ───────────────────────────────────────────────────────────────
# libpq-dev  → psycopg2-binary native compile fallback
# gcc        → C extensions (APScheduler / some wheels)
# curl       → healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq-dev \
        gcc \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Install Python deps (layer cached until requirements.txt changes) ─────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ── Copy source code ──────────────────────────────────────────────────────────
COPY . .

# ── Non-root user (security best practice) ───────────────────────────────────
RUN adduser --disabled-password --gecos "" appuser \
 && chown -R appuser:appuser /app
USER appuser

# ── Runtime config ────────────────────────────────────────────────────────────
ENV FLASK_ENV=production \
    PORT=3083 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 3083

# ── Healthcheck ───────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:3083/api/v1/health || exit 1

# ── Start with Gunicorn (production WSGI) ────────────────────────────────────
# --workers 1      → MQTT client + APScheduler ต้องอยู่ใน process เดียว
# --threads 8      → Pi4 (4 cores): 8 threads รองรับ SSE ได้ไม่ทำ thread exhaustion
# --worker-class   → ใช้ gthread จาก gunicorn.conf.py
# --timeout 120    → SSE connections ไม่ timeout เร็วเกินไป
CMD ["gunicorn", \
     "--config", "gunicorn.conf.py", \
     "--bind", "0.0.0.0:3083", \
     "--workers", "1", \
     "--threads", "16", \
     "--timeout", "120", \
     "--worker-class", "gthread", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "wsgi:app"]
