import json
import queue as queue_module

from flask import Blueprint, Response, request, stream_with_context

from app.services.device_service import DeviceService
from app.utils.helpers import error_response, is_valid_mac, require_auth, success_response

device_bp = Blueprint("device", __name__, url_prefix="/devices")

@device_bp.route("/register", methods=["POST"])
def register_device():
    """
    POST /api/v1/devices/register
    Request Body (JSON):
    {
        "mac_address":  "A4:CF:12:7E:3B:01",
        "model":        "IoT Plant Water",
        "model_serial": "208000001",
        "status_relay": [false, false, false, false]
    }
    """
    body = request.get_json(silent=True)
    if not body:
        return error_response("Request body must be JSON", 400)

    mac_address  = body.get("mac_address",  "").strip()
    model        = body.get("model",        "").strip()
    model_serial = body.get("model_serial", "").strip()
    status_relay = body.get("status_relay", [False, False, False, False])

    errors = {}
    if not mac_address:
        errors["mac_address"] = "mac_address is required"
    elif not is_valid_mac(mac_address):
        errors["mac_address"] = f"Invalid MAC address: '{mac_address}' (e.g. A4:CF:12:7E:3B:01)"
    if not model:
        errors["model"] = "model is required"
    if not model_serial:
        errors["model_serial"] = "model_serial is required"
    if not isinstance(status_relay, list):
        errors["status_relay"] = "status_relay must be an array"
    elif len(status_relay) != 4:
        errors["status_relay"] = f"status_relay must have exactly 4 elements, got {len(status_relay)}"
    elif not all(isinstance(v, bool) for v in status_relay):
        errors["status_relay"] = "status_relay elements must be boolean (true/false)"

    if errors:
        return error_response("Validation failed", 422, errors)

    try:
        result = DeviceService.register_device(mac_address, model, model_serial, status_relay)
    except Exception as exc:
        return error_response(f"Internal server error: {str(exc)}", 500)

    if result["is_new_registration"]:
        return success_response(result["device"], "Device registered successfully", 201)
    else:
        return success_response(result["device"], "Device already registered", 200)

@device_bp.route("/", methods=["GET"])
@require_auth
def list_devices():
    """
    GET /api/v1/devices/
    Headers: Authorization: Bearer <access_token>
    """
    try:
        page     = int(request.args.get("page", 1))
        per_page = min(int(request.args.get("per_page", 100)), 100)
    except ValueError:
        return error_response("page and per_page must be integers", 400)

    result = DeviceService.list_devices(page=page, per_page=per_page)
    return success_response(result, "Devices retrieved successfully", 200)

@device_bp.route("/<string:device_id>", methods=["GET"])
@require_auth
def get_device(device_id: str):
    """GET /api/v1/devices/<device_id>"""
    device = DeviceService.get_device_by_id(device_id)
    if not device:
        return error_response(f"Device not found: {device_id}", 404)
    return success_response(device.to_dict(), "Device found", 200)

@device_bp.route("/<string:device_id>/relay", methods=["PATCH"])
@require_auth
def update_relay(device_id: str):
    """
    PATCH /api/v1/devices/<device_id>/relay

    Request Body (JSON):
    {
        "channel": 0,      (0-3)
        "value":   true    (true=ON / false=OFF)
    }

    Response 200:
    { "status": "success", "message": "Command sent", "data": {...} }
    """
    from app.mqtt_client import mqtt_manager

    body = request.get_json(silent=True)
    if not body:
        return error_response("Request body must be JSON", 400)

    channel = body.get("channel")
    value   = body.get("value")

    if channel is None:
        return error_response("channel is required (0-3)", 422)
    if not isinstance(channel, int) or channel not in (0, 1, 2, 3):
        return error_response("channel must be an integer 0-3", 422)
    if value is None or not isinstance(value, bool):
        return error_response("value must be boolean (true/false)", 422)

    device = DeviceService.get_device_by_id(device_id)
    if not device:
        return error_response(f"Not found device: {device_id}", 404)

    published = mqtt_manager.publish_relay_command(device_id, channel, value)

    return success_response(
        {
            "device_id": device_id,
            "channel":   channel,
            "value":     value,
            "mqtt_sent": published,
        },
        "Command sent" if published else "Command queued (MQTT offline)",
        200,
    )

@device_bp.route("/rain/latest", methods=["GET"])
@require_auth
def get_rain_latest():
    """
    GET /api/v1/devices/rain/latest?device_id=<uuid>
    คืนข้อมูล rain sensor ล่าสุด
    """
    from app.services.rain_service import RainService

    device_id = request.args.get("device_id", "").strip()
    if not device_id:
        return error_response("device_id is required", 400)

    result = RainService.get_latest(device_id)
    if result is None:
        return success_response(None, "No rain data yet", 200)
    return success_response(result, "Rain status retrieved", 200)


@device_bp.route("/rain/history", methods=["GET"])
@require_auth
def get_rain_history():
    """
    GET /api/v1/devices/rain/history?device_id=<uuid>&limit=50
    คืนประวัติ rain sensor ล่าสุด
    """
    from app.services.rain_service import RainService

    device_id = request.args.get("device_id", "").strip()
    if not device_id:
        return error_response("device_id is required", 400)

    try:
        limit = min(int(request.args.get("limit", 50)), 200)
    except ValueError:
        return error_response("limit must be an integer", 400)

    entries = RainService.get_history(device_id, limit=limit)
    return success_response({"history": entries, "total": len(entries)}, "History retrieved", 200)


@device_bp.route("/events", methods=["GET"])
@require_auth
def device_events():
    """
    GET /api/v1/devices/events
    """
    from app.mqtt_client import mqtt_manager

    q = mqtt_manager.subscribe_sse()

    def generate():
        yield ": " + " " * 2048 + "\n\n"
        yield "event: ping\ndata: {}\n\n"
        try:
            while True:
                try:
                    data = q.get(timeout=15)
                    yield f"data: {json.dumps(data)}\n\n"
                except queue_module.Empty:
                    yield "event: ping\ndata: {}\n\n"
        finally:
            mqtt_manager.unsubscribe_sse(q)

    resp = Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
    )
    resp.headers["Cache-Control"]     = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp

