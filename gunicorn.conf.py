"""
Gunicorn configuration for IoT_208 Service

IMPORTANT — ใช้ 1 worker + threads เท่านั้น
เพราะ MQTT client และ APScheduler ต้องรันใน process เดียว
หลาย worker = หลาย MQTT connections = push notification ซ้ำ
"""

import multiprocessing

# ── Workers ───────────────────────────────────────────────────────────────────
workers     = 1                       # 1 worker เท่านั้น (MQTT / Scheduler)
threads     = multiprocessing.cpu_count() * 2 + 1  # Thread-based concurrency
worker_class = "gthread"

# ── Network ───────────────────────────────────────────────────────────────────
bind        = "0.0.0.0:5000"
timeout     = 120
keepalive   = 5

# ── Logging ───────────────────────────────────────────────────────────────────
accesslog   = "-"
errorlog    = "-"
loglevel    = "info"
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(D)sµs'

# ── Process ───────────────────────────────────────────────────────────────────
preload_app = False
