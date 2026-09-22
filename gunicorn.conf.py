"""
Gunicorn configuration for IoT_208 Service

IMPORTANT — ใช้ 1 worker + threads เท่านั้น
เพราะ MQTT client และ APScheduler ต้องรันใน process เดียว
หลาย worker = หลาย MQTT connections = push notification ซ้ำ

WHY gthread (not gevent):
  paho-mqtt และ APScheduler ต่างมี threading model ของตัวเอง
  Gevent monkey-patch ทำให้ทั้งสองพัง → ใช้ gthread (OS threads) แทน

Thread sizing (Raspberry Pi 4 — 4 cores, 4-8 GB RAM):
  - แต่ละ SSE /devices/events กิน 1 thread ตลอด lifetime
  - API calls ทั่วไปใช้เวลา < 100 ms → queue ได้
  - 16 threads ใช้ RAM ~64 MB (4 MB/thread stack) = เบามากสำหรับ Pi4
  - ปลอดภัย: 2 SSE connections + 14 threads ว่างสำหรับ API
"""

# ── Workers ───────────────────────────────────────────────────────────────────
workers      = 1                  # 1 worker เท่านั้น (MQTT / Scheduler)
threads      = 16                 # Pi4: 4 cores, 4-8 GB RAM → 16 threads สบาย
worker_class = "gthread"

# ── Network ───────────────────────────────────────────────────────────────────
bind         = "0.0.0.0:3083"
timeout      = 120
keepalive    = 5

# ── Performance ───────────────────────────────────────────────────────────────
worker_connections = 1000         # max concurrent clients per worker
backlog            = 512          # pending connections queue

# ── Logging ───────────────────────────────────────────────────────────────────
accesslog   = "-"
errorlog    = "-"
loglevel    = "warning"
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(D)sµs'

# ── Process ───────────────────────────────────────────────────────────────────
preload_app = False               # False เพราะ 1 worker ไม่มี fork
