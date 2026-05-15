import re

from flask import Blueprint, request

import jwt as pyjwt

from app.services.auth_service import AuthService
from app.utils.helpers import (
    decode_jwt,
    error_response,
    generate_access_token,
    require_auth,
    success_response,
)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

def _is_valid_email(email: str) -> bool:
    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))

@auth_bp.route("/signup", methods=["POST"])
def signup():
    """
    POST /api/v1/auth/signup

    Request Body (JSON):
    {
        "mem_firstname": "สมชาย",
        "mem_lastname":  "ใจดี",
        "mem_email":     "somchai@example.com",
        "mem_phone":     "0812345678",        (optional)
        "mem_fcm":       "fcm_token_here",    (optional)
        "mem_username":  "somchai01",
        "mem_password":  "mySecurePass123"
    }

    Response 201:
    {
        "status":  "success",
        "message": "สมัครสมาชิกสำเร็จ",
        "data":    { member object }
    }
    """
    body = request.get_json(silent=True)
    if not body:
        return error_response("Request body must be JSON", 400)

    errors = {}

    mem_firstname = body.get("mem_firstname", "").strip()
    mem_lastname  = body.get("mem_lastname",  "").strip()
    mem_email     = body.get("mem_email",     "").strip()
    mem_username  = body.get("mem_username",  "").strip()
    mem_password  = body.get("mem_password",  "").strip()
    mem_phone     = body.get("mem_phone",     "")
    mem_fcm       = body.get("mem_fcm",       "")

    if not mem_firstname:
        errors["mem_firstname"] = "กรุณากรอกชื่อจริง"
    if not mem_lastname:
        errors["mem_lastname"] = "กรุณากรอกนามสกุล"
    if not mem_email:
        errors["mem_email"] = "กรุณากรอกอีเมล"
    elif not _is_valid_email(mem_email):
        errors["mem_email"] = "รูปแบบอีเมลไม่ถูกต้อง"
    if not mem_username:
        errors["mem_username"] = "กรุณากรอกชื่อผู้ใช้"
    elif len(mem_username) < 4:
        errors["mem_username"] = "ชื่อผู้ใช้ต้องมีอย่างน้อย 4 ตัวอักษร"
    if not mem_password:
        errors["mem_password"] = "กรุณากรอกรหัสผ่าน"
    elif len(mem_password) < 6:
        errors["mem_password"] = "รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร"

    if errors:
        return error_response("ข้อมูลไม่ถูกต้อง", 422, errors)

    try:
        member = AuthService.signup({
            "mem_firstname": mem_firstname,
            "mem_lastname":  mem_lastname,
            "mem_email":     mem_email,
            "mem_phone":     mem_phone,
            "mem_fcm":       mem_fcm,
            "mem_username":  mem_username,
            "mem_password":  mem_password,
        })
        return success_response(member, "สมัครสมาชิกสำเร็จ", 201)

    except ValueError as exc:
        return error_response(str(exc), 409)
    except Exception as exc:
        return error_response(f"เกิดข้อผิดพลาด: {str(exc)}", 500)

@auth_bp.route("/login", methods=["POST"])
def login():
    """
    POST /api/v1/auth/login

    Request Body (JSON):
    {
        "mem_username": "somchai01",
        "mem_password": "mySecurePass123",
        "mem_fcm":      "fcm_token_here"   (optional — อัปเดต token หลัง login)
    }

    Response 200:
    {
        "status":  "success",
        "message": "เข้าสู่ระบบสำเร็จ",
        "data":    { member object }
    }
    """
    body = request.get_json(silent=True)
    if not body:
        return error_response("Request body must be JSON", 400)

    mem_username = body.get("mem_username", "").strip()
    mem_password = body.get("mem_password", "").strip()
    mem_fcm      = body.get("mem_fcm", "")

    errors = {}
    if not mem_username:
        errors["mem_username"] = "กรุณากรอกชื่อผู้ใช้"
    if not mem_password:
        errors["mem_password"] = "กรุณากรอกรหัสผ่าน"

    if errors:
        return error_response("ข้อมูลไม่ถูกต้อง", 422, errors)

    try:
        result = AuthService.login(mem_username, mem_password, mem_fcm or None)
        return success_response(result, "เข้าสู่ระบบสำเร็จ", 200)

    except ValueError as exc:
        return error_response(str(exc), 401)
    except Exception as exc:
        return error_response(f"เกิดข้อผิดพลาด: {str(exc)}", 500)

@auth_bp.route("/refresh", methods=["POST"])
def refresh_token():
    """
    POST /api/v1/auth/refresh

    Request Body (JSON):
    {
        "refresh_token": "<refresh_jwt>"
    }

    Response 200:
    {
        "status":  "success",
        "message": "Token refreshed",
        "data":    { "access_token": "<new_access_jwt>" }
    }
    """
    body = request.get_json(silent=True)
    if not body:
        return error_response("Request body must be JSON", 400)

    rt = body.get("refresh_token", "").strip()
    if not rt:
        return error_response("refresh_token is required", 422)

    try:
        payload = decode_jwt(rt)

        if payload.get("type") != "refresh":
            return error_response("Invalid token type", 401)

        mem_id = payload.get("mem_id")

        member = AuthService.get_member_by_id(mem_id)
        if not member:
            return error_response("ไม่พบสมาชิก", 401)

        new_access_token = generate_access_token(member.mem_id, member.mem_username)
        return success_response({"access_token": new_access_token}, "Token refreshed", 200)

    except pyjwt.ExpiredSignatureError:
        return error_response("Refresh token หมดอายุ กรุณาเข้าสู่ระบบใหม่", 401)
    except pyjwt.InvalidTokenError:
        return error_response("Refresh token ไม่ถูกต้อง", 401)
    except Exception as exc:
        return error_response(f"เกิดข้อผิดพลาด: {str(exc)}", 500)

@auth_bp.route("/fcm-token", methods=["PUT"])
@require_auth
def put_fcm_token():
    """
    PUT /api/v1/auth/fcm-token  (JWT required)

    Request Headers:
        Authorization: Bearer <access_token>

    Request Body (JSON):
    {
        "mem_fcm": "new_fcm_token_here"
    }

    Response 200:
    {
        "status":  "success",
        "message": "อัปเดต FCM token สำเร็จ",
        "data":    { member object }
    }
    """
    mem_id  = request.current_user.get("mem_id")
    body    = request.get_json(silent=True)
    if not body:
        return error_response("Request body must be JSON", 400)

    mem_fcm = body.get("mem_fcm", "").strip()
    if not mem_fcm:
        return error_response("mem_fcm is required", 422)

    try:
        member = AuthService.update_fcm_token(int(mem_id), mem_fcm)
        return success_response(member, "อัปเดต FCM token สำเร็จ", 200)
    except ValueError as exc:
        return error_response(str(exc), 404)
    except Exception as exc:
        return error_response(f"เกิดข้อผิดพลาด: {str(exc)}", 500)


@auth_bp.route("/fcm-token", methods=["PATCH"])
def update_fcm_token():
    """
    PATCH /api/v1/auth/fcm-token

    Request Body (JSON):
    {
        "mem_id":    1,
        "mem_fcm":   "new_fcm_token_here"
    }
    """
    body = request.get_json(silent=True)
    if not body:
        return error_response("Request body must be JSON", 400)

    mem_id  = body.get("mem_id")
    mem_fcm = body.get("mem_fcm", "").strip()

    if not mem_id:
        return error_response("mem_id is required", 422)
    if not mem_fcm:
        return error_response("mem_fcm is required", 422)

    try:
        member = AuthService.update_fcm_token(int(mem_id), mem_fcm)
        return success_response(member, "อัปเดต FCM token สำเร็จ", 200)
    except ValueError as exc:
        return error_response(str(exc), 404)
    except Exception as exc:
        return error_response(f"เกิดข้อผิดพลาด: {str(exc)}", 500)
