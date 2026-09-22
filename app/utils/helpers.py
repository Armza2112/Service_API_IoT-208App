"""
Utility helpers สำหรับโปรเจกต์
"""
import re
import uuid
import datetime
import os
from functools import wraps

import jwt
from flask import request


def generate_device_id() -> str:
    """
    สร้าง Device ID แบบ UUID4 ที่ไม่ซ้ำกัน
    Format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    """
    return str(uuid.uuid4())


def normalize_mac(mac: str) -> str:
    """
    Normalize MAC address ให้เป็นรูปแบบ uppercase XX:XX:XX:XX:XX:XX
    รองรับทั้ง ':' และ '-' และ ไม่มี separator
    """
    clean = re.sub(r"[:\-\.]", "", mac).upper()
    if len(clean) != 12:
        raise ValueError(f"MAC address '{mac}' ไม่ถูกต้อง (ต้องมี 12 hex characters)")
    return ":".join(clean[i : i + 2] for i in range(0, 12, 2))


def is_valid_mac(mac: str) -> bool:
    """ตรวจสอบว่า MAC address ถูกรูปแบบหรือไม่"""
    pattern = r"^([0-9A-Fa-f]{2}[:\-]){5}([0-9A-Fa-f]{2})$"
    return bool(re.match(pattern, mac))


def _jwt_secret() -> str:
    return os.getenv("JWT_SECRET_KEY") or os.getenv("SECRET_KEY", "dev-secret-key")


def generate_access_token(mem_id: int, mem_username: str) -> str:
    """
    สร้าง Access Token อายุ 1 ชั่วโมง
    """
    payload = {
        "sub":          str(mem_id),
        "mem_id":       mem_id,
        "mem_username": mem_username,
        "type":         "access",
        "iat":          datetime.datetime.utcnow(),
        "exp":          datetime.datetime.utcnow() + datetime.timedelta(hours=1),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def generate_refresh_token(mem_id: int) -> str:
    """
    สร้าง Refresh Token อายุ 30 วัน
    """
    payload = {
        "sub":    str(mem_id),
        "mem_id": mem_id,
        "type":   "refresh",
        "iat":    datetime.datetime.utcnow(),
        "exp":    datetime.datetime.utcnow() + datetime.timedelta(days=30),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


# Keep backward-compat alias
def generate_jwt(mem_id: int, mem_username: str) -> str:
    return generate_access_token(mem_id, mem_username)


def decode_jwt(token: str) -> dict:
    """
    Decode และ verify JWT token
    Raises jwt.ExpiredSignatureError หรือ jwt.InvalidTokenError ถ้าไม่ valid
    """
    return jwt.decode(token, _jwt_secret(), algorithms=["HS256"])


def _hmi_api_key() -> str:
    return os.getenv("HMI_API_KEY", "")


def require_auth(f):
    """
    Decorator ตรวจสอบ JWT access token หรือ HMI API key
    ลำดับตรวจ:
      1. X-Api-Key: <key>              (HMI screen — ไม่ต้อง login)
      2. Authorization: Bearer <token> (ปกติ)
      3. ?token=<token>                (SSE / EventSource)
    ถ้า valid → ใส่ payload ไว้ใน request.current_user
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # 1. HMI API key (no login required)
        api_key = request.headers.get("X-Api-Key", "").strip()
        hmi_key = _hmi_api_key()
        if api_key and hmi_key and api_key == hmi_key:
            request.current_user = {"mem_id": 0, "mem_username": "hmi_screen", "type": "access"}
            return f(*args, **kwargs)

        # 2. Bearer JWT
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
        else:
            # 3. Query param fallback
            token = request.args.get("token", "").strip()

        if not token:
            return error_response("Authorization required", 401)

        try:
            payload = decode_jwt(token)
            if payload.get("type") != "access":
                return error_response("Invalid token type", 401)
            request.current_user = payload
        except jwt.ExpiredSignatureError:
            return error_response("Token หมดอายุ", 401)
        except jwt.InvalidTokenError:
            return error_response("Token ไม่ถูกต้อง", 401)
        return f(*args, **kwargs)
    return decorated


def success_response(data: dict | list, message: str = "Success", status_code: int = 200) -> tuple:
    """สร้าง standard success response"""
    return {
        "status": "success",
        "message": message,
        "data": data,
    }, status_code


def error_response(message: str, status_code: int = 400, errors: dict = None) -> tuple:
    """สร้าง standard error response"""
    body = {
        "status": "error",
        "message": message,
    }
    if errors:
        body["errors"] = errors
    return body, status_code
