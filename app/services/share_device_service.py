from app.entities.share_device_entity import ShareDevice
from app.entities.member_entity import MbMem
from app.entities.device_profile_entity import DeviceProfile
from app.extensions import db


class ShareDeviceService:

    @staticmethod
    def search_member(username: str, requester_mem_id: int) -> dict | None:
        member = MbMem.query.filter(
            MbMem.mem_username == username,
            MbMem.mem_id != requester_mem_id,
        ).first()
        if not member:
            return None
        return {
            "mem_id":        member.mem_id,
            "mem_username":  member.mem_username,
            "mem_firstname": member.mem_firstname,
            "mem_lastname":  member.mem_lastname,
        }

    @staticmethod
    def share_device(owner_mem_id: int, shared_mem_id: int, device_id: str) -> dict:
        device = DeviceProfile.query.filter_by(device_id=device_id).first()
        if not device:
            raise ValueError(f"ไม่พบอุปกรณ์ device_id={device_id}")

        shared_mem = MbMem.query.filter_by(mem_id=shared_mem_id).first()
        if not shared_mem:
            raise ValueError("ไม่พบ member ที่จะแชร์ให้")

        exists = ShareDevice.query.filter_by(
            owner_mem_id=owner_mem_id,
            shared_mem_id=shared_mem_id,
            device_id=device_id,
        ).first()
        if exists:
            raise ValueError("แชร์อุปกรณ์นี้ให้ผู้ใช้นี้ไปแล้ว")

        share = ShareDevice(
            owner_mem_id=owner_mem_id,
            shared_mem_id=shared_mem_id,
            device_id=device_id,
        )
        db.session.add(share)
        db.session.commit()
        db.session.refresh(share)
        return share.to_dict()

    @staticmethod
    def get_my_shares(owner_mem_id: int) -> list[dict]:
        shares = ShareDevice.query.filter_by(owner_mem_id=owner_mem_id).all()
        result = []
        for s in shares:
            member = MbMem.query.filter_by(mem_id=s.shared_mem_id).first()
            device = DeviceProfile.query.filter_by(device_id=s.device_id).first()
            result.append({
                "id":          s.id,
                "device_id":   s.device_id,
                "device_model": device.model if device else None,
                "device_model_serial": device.model_serial if device else None,
                "shared_with": {
                    "mem_id":       member.mem_id       if member else None,
                    "mem_username": member.mem_username if member else None,
                    "mem_firstname": member.mem_firstname if member else None,
                    "mem_lastname":  member.mem_lastname  if member else None,
                },
                "created_at":  s.created_at.isoformat() if s.created_at else None,
            })
        return result

    @staticmethod
    def revoke_share(share_id: int, owner_mem_id: int) -> None:
        share = ShareDevice.query.filter_by(
            id=share_id, owner_mem_id=owner_mem_id
        ).first()
        if not share:
            raise ValueError("ไม่พบการแชร์นี้หรือคุณไม่มีสิทธิ์ลบ")
        db.session.delete(share)
        db.session.commit()
