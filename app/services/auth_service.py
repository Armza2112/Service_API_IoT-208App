from werkzeug.security import check_password_hash, generate_password_hash

from app.entities.member_entity import MbMem
from app.extensions import db
from app.utils.helpers import generate_access_token, generate_refresh_token


class AuthService:

    @staticmethod
    def signup(data: dict) -> dict:
        """
        Returns:
            { "member": {...}, "token": "jwt..." }
        """
        email    = data["mem_email"].strip().lower()
        username = data["mem_username"].strip()

        if MbMem.query.filter_by(mem_email=email).first():
            raise ValueError("อีเมลนี้ถูกใช้งานแล้ว")

        if MbMem.query.filter_by(mem_username=username).first():
            raise ValueError("ชื่อผู้ใช้นี้ถูกใช้งานแล้ว")

        member = MbMem(
            mem_firstname = data["mem_firstname"].strip(),
            mem_lastname  = data["mem_lastname"].strip(),
            mem_email     = email,
            mem_phone     = data.get("mem_phone", "").strip() or None,
            mem_fcm       = data.get("mem_fcm", "").strip() or None,
            mem_username  = username,
            mem_password  = generate_password_hash(data["mem_password"]),
        )

        db.session.add(member)
        db.session.commit()

        access_token  = generate_access_token(member.mem_id, member.mem_username)
        refresh_token = generate_refresh_token(member.mem_id)

        return {
            "member":        member.to_dict(),
            "access_token":  access_token,
            "refresh_token": refresh_token,
        }

    @staticmethod
    def login(username: str, password: str, fcm_token: str | None = None) -> dict:
        member = MbMem.query.filter_by(mem_username=username.strip()).first()

        if not member or not check_password_hash(member.mem_password, password):
            raise ValueError("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")

        if fcm_token and fcm_token.strip():
            member.mem_fcm = fcm_token.strip()
            db.session.commit()

        access_token  = generate_access_token(member.mem_id, member.mem_username)
        refresh_token = generate_refresh_token(member.mem_id)

        return {
            "member":        member.to_dict(),
            "access_token":  access_token,
            "refresh_token": refresh_token,
        }

    # ── Update FCM Token ──────────────────────────────────────
    @staticmethod
    def update_fcm_token(mem_id: int, fcm_token: str) -> dict:
        member = MbMem.query.get(mem_id)
        if not member:
            raise ValueError(f"ไม่พบสมาชิก mem_id={mem_id}")

        member.mem_fcm = fcm_token.strip()
        db.session.commit()

        return member.to_dict()

    # ── Get Member ────────────────────────────────────────────
    @staticmethod
    def get_member_by_id(mem_id: int):
        return MbMem.query.get(mem_id)
