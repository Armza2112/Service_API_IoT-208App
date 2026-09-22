import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration."""

    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"

    # PostgreSQL
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "iot_db")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    SQLALCHEMY_DATABASE_URI = (
        f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── Connection pool ───────────────────────────────────────────────────────
    # gthread: 16 threads → ต้องการ DB connections พร้อมกันสูงสุด ~16
    # pool_size=10 + max_overflow=10 = สูงสุด 20 connections ซึ่งเกินพอ
    # pool_timeout: รอ connection ว่างสูงสุด 10 วิ ก่อน timeout
    # pool_recycle: คืน connection ทุก 30 นาที ป้องกัน stale connection
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size":    10,
        "max_overflow": 10,
        "pool_timeout": 10,
        "pool_recycle": 1800,
        "pool_pre_ping": True,    # ตรวจ connection ก่อนใช้ ป้องกัน "server closed connection"
    }

    # JWT
    JWT_SECRET_KEY       = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_EXPIRE_DAYS      = int(os.getenv("JWT_EXPIRE_DAYS", "7"))

    CORS_ORIGINS         = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    CORS_SUPPORTS_CREDENTIALS = True

    MQTT_BROKER    = os.getenv("MQTT_BROKER",    "localhost")
    MQTT_PORT      = int(os.getenv("MQTT_PORT",  "1883"))
    MQTT_USERNAME  = os.getenv("MQTT_USERNAME",  "")
    MQTT_PASSWORD  = os.getenv("MQTT_PASSWORD",  "")
    MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "iot208-backend")
    MQTT_TRANSPORT = os.getenv("MQTT_TRANSPORT", "tcp")
    MQTT_WS_PATH   = os.getenv("MQTT_WS_PATH",   "/mqtt")

    # Pagination / misc
    JSON_SORT_KEYS = False


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
