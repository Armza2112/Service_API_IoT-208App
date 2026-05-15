"""
Share Device Controller
GET    /api/v1/share/search?username=xxx  
GET    /api/v1/share/                     
POST   /api/v1/share/                     
DELETE /api/v1/share/<int:share_id>       
"""
from flask import Blueprint, request

from app.services.share_device_service import ShareDeviceService
from app.utils.helpers import error_response, require_auth, success_response

share_bp = Blueprint("share", __name__, url_prefix="/share")


@share_bp.route("/search", methods=["GET"])
@require_auth
def search_member():
    username = request.args.get("username", "").strip()
    if not username:
        return error_response("username is required", 422)

    owner_mem_id = request.current_user["mem_id"]
    member = ShareDeviceService.search_member(username, owner_mem_id)
    if not member:
        return error_response("ไม่พบผู้ใช้", 404)

    return success_response(member, "พบผู้ใช้", 200)


@share_bp.route("/", methods=["GET"], strict_slashes=False)
@require_auth
def get_shares():
    owner_mem_id = request.current_user["mem_id"]
    shares = ShareDeviceService.get_my_shares(owner_mem_id)
    return success_response(shares, "รายการการแชร์", 200)


@share_bp.route("/", methods=["POST"], strict_slashes=False)
@require_auth
def share_device():
    body = request.get_json(silent=True)
    if not body:
        return error_response("Request body must be JSON", 400)

    shared_mem_id = body.get("shared_mem_id")
    device_id     = body.get("device_id", "").strip()
    owner_mem_id  = request.current_user["mem_id"]

    if not shared_mem_id:
        return error_response("shared_mem_id is required", 422)
    if not device_id:
        return error_response("device_id is required", 422)
    if int(shared_mem_id) == owner_mem_id:
        return error_response("ไม่สามารถแชร์ให้ตัวเองได้", 422)

    try:
        share = ShareDeviceService.share_device(owner_mem_id, int(shared_mem_id), device_id)
        return success_response(share, "แชร์อุปกรณ์สำเร็จ", 201)
    except ValueError as exc:
        return error_response(str(exc), 409)
    except Exception as exc:
        return error_response(f"เกิดข้อผิดพลาด: {str(exc)}", 500)


@share_bp.route("/<int:share_id>", methods=["DELETE"])
@require_auth
def revoke_share(share_id: int):
    owner_mem_id = request.current_user["mem_id"]
    try:
        ShareDeviceService.revoke_share(share_id, owner_mem_id)
        return success_response(None, "ยกเลิกการแชร์สำเร็จ", 200)
    except ValueError as exc:
        return error_response(str(exc), 404)
    except Exception as exc:
        return error_response(f"เกิดข้อผิดพลาด: {str(exc)}", 500)
