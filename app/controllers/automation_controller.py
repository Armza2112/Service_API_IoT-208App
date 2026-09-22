import re

from flask import Blueprint, request

from app.services.automation_service import AutomationService
from app.services.device_service import DeviceService
from app.utils.helpers import error_response, require_auth, success_response

_DOOR_MODEL_SERIAL_PREFIX = "iotcontrollerdoor"  # lowercase startswith check

automation_bp = Blueprint("automation", __name__, url_prefix="/automations")

_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def _validate_time(t: str) -> bool:
    if not _TIME_RE.match(t):
        return False
    h, m = int(t[:2]), int(t[3:])
    return 0 <= h <= 23 and 0 <= m <= 59


def _validate_days(days) -> bool:
    if not isinstance(days, list) or len(days) == 0:
        return False
    return all(isinstance(d, int) and 0 <= d <= 6 for d in days)


@automation_bp.route("/", methods=["GET"])
@require_auth
def list_automations():
    items = AutomationService.list_all()
    return success_response([a.to_dict() for a in items], "OK", 200)


@automation_bp.route("/", methods=["POST"])
@require_auth
def create_automation():
    mem_id = request.current_user["mem_id"]
    body   = request.get_json(silent=True)
    if not body:
        return error_response("Request body must be JSON", 400)

    name             = (body.get("name") or "").strip()
    device_id        = (body.get("device_id") or "").strip()
    channel          = body.get("channel")
    action           = body.get("action")
    trigger_time     = (body.get("trigger_time") or "").strip()
    trigger_days     = body.get("trigger_days")
    duration_minutes = body.get("duration_minutes")   # optional int
    skip_if_raining  = body.get("skip_if_raining", False)
    until_float_off  = body.get("until_float_off", False)

    errors = {}
    if not name:
        errors["name"] = "name is required"
    elif len(name) > 100:
        errors["name"] = "name must be <= 100 characters"
    if not device_id:
        errors["device_id"] = "device_id is required"
    if channel is None or not isinstance(channel, int) or channel not in range(4):
        errors["channel"] = "channel must be 0-3"
    if action is None or not isinstance(action, bool):
        errors["action"] = "action must be true or false"
    if not trigger_time or not _validate_time(trigger_time):
        errors["trigger_time"] = "trigger_time must be HH:MM (00:00-23:59)"
    if not _validate_days(trigger_days):
        errors["trigger_days"] = "trigger_days must be a non-empty list of ints 0-6"
    if duration_minutes is not None and (
        not isinstance(duration_minutes, int) or duration_minutes < 1 or duration_minutes > 480
    ):
        errors["duration_minutes"] = "duration_minutes must be an integer 1-480"
    if not isinstance(skip_if_raining, bool):
        errors["skip_if_raining"] = "skip_if_raining must be true or false"
    if not isinstance(until_float_off, bool):
        errors["until_float_off"] = "until_float_off must be true or false"

    if errors:
        return error_response("Validation failed", 422, errors)

    # Door device: automation not supported
    device = DeviceService.get_device_by_id(device_id)
    if device and device.model_serial.lower().startswith(_DOOR_MODEL_SERIAL_PREFIX):
        return error_response("ไม่รองรับ Automation สำหรับ Door controller", 422)

    try:
        auto = AutomationService.create(
            mem_id=mem_id,
            name=name,
            device_id=device_id,
            channel=channel,
            action=action,
            trigger_time=trigger_time,
            trigger_days=trigger_days,
            duration_minutes=duration_minutes,
            skip_if_raining=skip_if_raining,
            until_float_off=until_float_off,
        )
    except Exception as exc:
        return error_response(str(exc), 500)

    try:
        from app.scheduler import scheduler_manager
        scheduler_manager.add_job(auto)
    except Exception:
        pass

    return success_response(auto.to_dict(), "Automation created", 201)


@automation_bp.route("/<int:automation_id>", methods=["PATCH"])
@require_auth
def update_automation(automation_id: int):
    body   = request.get_json(silent=True) or {}
    kwargs = {}
    errors = {}

    if "name" in body:
        n = (body["name"] or "").strip()
        if not n:
            errors["name"] = "name cannot be empty"
        elif len(n) > 100:
            errors["name"] = "name must be <= 100 characters"
        else:
            kwargs["name"] = n

    if "device_id" in body:
        d = (body["device_id"] or "").strip()
        if not d:
            errors["device_id"] = "device_id cannot be empty"
        else:
            kwargs["device_id"] = d

    if "channel" in body:
        c = body["channel"]
        if not isinstance(c, int) or c not in range(4):
            errors["channel"] = "channel must be 0-3"
        else:
            kwargs["channel"] = c

    if "action" in body:
        a = body["action"]
        if not isinstance(a, bool):
            errors["action"] = "action must be true or false"
        else:
            kwargs["action"] = a

    if "trigger_time" in body:
        t = (body["trigger_time"] or "").strip()
        if not _validate_time(t):
            errors["trigger_time"] = "trigger_time must be HH:MM (00:00-23:59)"
        else:
            kwargs["trigger_time"] = t

    if "trigger_days" in body:
        days = body["trigger_days"]
        if not _validate_days(days):
            errors["trigger_days"] = "trigger_days must be a non-empty list of ints 0-6"
        else:
            kwargs["trigger_days"] = days

    if "skip_if_raining" in body:
        sir = body["skip_if_raining"]
        if not isinstance(sir, bool):
            errors["skip_if_raining"] = "skip_if_raining must be true or false"
        else:
            kwargs["skip_if_raining"] = sir

    if "until_float_off" in body:
        ufo = body["until_float_off"]
        if not isinstance(ufo, bool):
            errors["until_float_off"] = "until_float_off must be true or false"
        else:
            kwargs["until_float_off"] = ufo

    if "duration_minutes" in body:
        dm = body["duration_minutes"]
        if dm is None:
            kwargs["duration_minutes"] = None
        elif not isinstance(dm, int) or dm < 1 or dm > 480:
            errors["duration_minutes"] = "duration_minutes must be an integer 1-480"
        else:
            kwargs["duration_minutes"] = dm

    if errors:
        return error_response("Validation failed", 422, errors)

    try:
        auto = AutomationService.update(automation_id, **kwargs)
    except ValueError as exc:
        return error_response(str(exc), 404)
    except Exception as exc:
        return error_response(str(exc), 500)

    try:
        from app.scheduler import scheduler_manager
        scheduler_manager.reschedule_job(auto)
    except Exception:
        pass

    return success_response(auto.to_dict(), "Automation updated", 200)


@automation_bp.route("/<int:automation_id>/toggle", methods=["PATCH"])
@require_auth
def toggle_automation(automation_id: int):
    try:
        auto = AutomationService.toggle(automation_id)
    except ValueError as exc:
        return error_response(str(exc), 404)
    except Exception as exc:
        return error_response(str(exc), 500)

    try:
        from app.scheduler import scheduler_manager
        if auto.is_enabled:
            scheduler_manager.resume_job(auto.id)
        else:
            scheduler_manager.pause_job(auto.id)
    except Exception:
        pass

    return success_response(auto.to_dict(), "Automation toggled", 200)


@automation_bp.route("/<int:automation_id>", methods=["DELETE"])
@require_auth
def delete_automation(automation_id: int):
    try:
        AutomationService.delete(automation_id)
    except ValueError as exc:
        return error_response(str(exc), 404)
    except Exception as exc:
        return error_response(str(exc), 500)

    try:
        from app.scheduler import scheduler_manager
        scheduler_manager.remove_job(automation_id)
    except Exception:
        pass

    return success_response(None, "Automation deleted", 200)
