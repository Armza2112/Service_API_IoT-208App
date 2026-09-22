"""
Flask Application Factory
"""
import importlib

from flask import Flask

from app.extensions import db, cors
from app.mqtt_client import mqtt_manager
from app.scheduler import scheduler_manager
from config.settings import config_map


def create_app(env: str = "default") -> Flask:
    flask_app = Flask(__name__)

    flask_app.config.from_object(config_map[env])
    db.init_app(flask_app)

    cors.init_app(
        flask_app,
        resources={r"/api/*": {
            "origins":         flask_app.config.get("CORS_ORIGINS", ["*"]),
            "allow_headers":   ["Content-Type", "Authorization"],
            "expose_headers":  ["Content-Type"],
            "methods":         ["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        }},
        supports_credentials=True,
    )

    # Auto-import all entities so db.create_all() sees every table
    importlib.import_module("app.entities")

    with flask_app.app_context():
        db.create_all()
        _run_migrations(flask_app)

    _register_blueprints(flask_app)
    _register_health(flask_app)
    _register_error_handlers(flask_app)

    mqtt_manager.init_app(flask_app)

    scheduler_manager.init_app(flask_app)

    return flask_app


def _run_migrations(flask_app: Flask) -> None:
    """
    Idempotent schema migrations — ADD COLUMN IF NOT EXISTS ทำให้รันซ้ำได้เรื่อย ๆ
    ใช้แทน Alembic สำหรับโปรเจกต์นี้เพราะไม่มี migration framework
    """
    migrations = [
        # ── automations table ─────────────────────────────────────────────────
        "ALTER TABLE automations ADD COLUMN IF NOT EXISTS duration_minutes INTEGER DEFAULT NULL;",
        "ALTER TABLE automations ADD COLUMN IF NOT EXISTS skip_if_raining  BOOLEAN NOT NULL DEFAULT false;",
        "ALTER TABLE automations ADD COLUMN IF NOT EXISTS until_float_off  BOOLEAN NOT NULL DEFAULT false;",
    ]
    try:
        with db.engine.connect() as conn:
            for sql in migrations:
                conn.execute(db.text(sql))
            conn.commit()
    except Exception as exc:
        # ถ้า table ยังไม่มี (รันก่อน create_all) หรือ error อื่น — ไม่ทำให้ app crash
        import logging
        logging.getLogger(__name__).warning("Migration warning: %s", exc)


def _register_blueprints(flask_app: Flask) -> None:
    from app.controllers.device_controller import device_bp
    from app.controllers.auth_controller import auth_bp
    from app.controllers.automation_controller import automation_bp
    from app.controllers.share_device_controller import share_bp

    api_v1_prefix = "/api/v1"

    flask_app.register_blueprint(
        device_bp,
        url_prefix=f"{api_v1_prefix}{device_bp.url_prefix}",
    )

    flask_app.register_blueprint(
        auth_bp,
        url_prefix=f"{api_v1_prefix}{auth_bp.url_prefix}",
    )

    flask_app.register_blueprint(
        automation_bp,
        url_prefix=f"{api_v1_prefix}{automation_bp.url_prefix}",
    )

    flask_app.register_blueprint(
        share_bp,
        url_prefix=f"{api_v1_prefix}{share_bp.url_prefix}",
    )


def _register_health(flask_app: Flask) -> None:
    @flask_app.get("/api/v1/health")
    def health():
        return {"status": "ok"}, 200


def _register_error_handlers(flask_app: Flask) -> None:
    @flask_app.errorhandler(404)
    def not_found(e):
        return {"status": "error", "message": "Endpoint not found"}, 404

    @flask_app.errorhandler(405)
    def method_not_allowed(e):
        return {"status": "error", "message": "Method not allowed"}, 405

    @flask_app.errorhandler(500)
    def internal_error(e):
        return {"status": "error", "message": "Internal Server Error"}, 500
