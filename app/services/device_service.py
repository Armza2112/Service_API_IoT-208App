from datetime import datetime, timezone, timedelta
from typing import List

from app.extensions import db
from app.entities.device_profile_entity import DeviceProfile
from app.utils.helpers import generate_device_id, normalize_mac


class DeviceService:

    @staticmethod
    def register_device(
        mac_address: str,
        model: str,
        model_serial: str,
        status_relay: List[bool] = None,
    ) -> dict:
        if status_relay is None:
            status_relay = [False, False, False, False]

        normalized_mac = normalize_mac(mac_address)

        existing = DeviceProfile.query.filter_by(mac_address=normalized_mac).first()
        if existing:
            return {"device": existing.to_dict(), "is_new_registration": False}

        device = DeviceProfile(
            device_id=generate_device_id(),
            mac_address=normalized_mac,
            model=model.strip(),
            model_serial=model_serial.strip(),
            status_relay=status_relay,
        )
        db.session.add(device)
        db.session.commit()

        return {"device": device.to_dict(), "is_new_registration": True}

    @staticmethod
    def get_device_by_id(device_id: str):
        return DeviceProfile.query.filter_by(device_id=device_id).first()

    @staticmethod
    def get_device_by_mac(mac_address: str):
        normalized_mac = normalize_mac(mac_address)
        return DeviceProfile.query.filter_by(mac_address=normalized_mac).first()

    @staticmethod
    def update_relay(device_id: str, channel: int, value: bool) -> dict:
        device = DeviceProfile.query.filter_by(device_id=device_id).first()
        if not device:
            raise ValueError(f"ไม่พบอุปกรณ์: {device_id}")

        if not (0 <= channel <= 3):
            raise ValueError(f"channel ต้องเป็น 0-3 ได้รับ: {channel}")

        new_relay = list(device.status_relay)
        new_relay[channel] = value
        device.status_relay = new_relay
        db.session.commit()
        db.session.refresh(device)
        return device.to_dict()

    @staticmethod
    def list_devices(page: int = 1, per_page: int = 20) -> dict:
        pagination = DeviceProfile.query.order_by(
            DeviceProfile.created_at.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)

        return {
            "devices": [d.to_dict() for d in pagination.items],
            "pagination": {
                "total": pagination.total,
                "pages": pagination.pages,
                "current_page": pagination.page,
                "per_page": pagination.per_page,
                "has_next": pagination.has_next,
                "has_prev": pagination.has_prev,
            },
        }

    # ── Role ──────────────────────────────────────────────────────────────────

    _VALID_ROLES = {"water_outside", "water_inside", "door_outside", "door_inside"}

    @staticmethod
    def get_roles() -> dict:
        """คืน {role: device_id | None} สำหรับทุก role ที่รองรับ"""
        result = {r: None for r in DeviceService._VALID_ROLES}
        devices = DeviceProfile.query.filter(
            DeviceProfile.role.in_(DeviceService._VALID_ROLES)
        ).all()
        for d in devices:
            result[d.role] = d.device_id
        return result

    @staticmethod
    def set_role(device_id: str, role: str | None) -> dict:
        """
        กำหนด role ให้ device — ถ้า role ซ้ำกับ device อื่น จะล้าง role เดิมออกก่อน
        role=None หมายถึงเอา role ออก
        """
        # ล