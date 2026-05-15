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

    _register_blueprints(flask_app)
    _register_health(flask_app)
    _register_error_handlers(flask_app)

    mqtt_manager.init_app(flask_app)

    scheduler_manager.init_app(flask_app)

    return flask_app


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
