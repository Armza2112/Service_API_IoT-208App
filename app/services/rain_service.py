import logging

from app.extensions import db
from app.entities.rain_history_entity import RainHistory

logger = logging.getLogger(__name__)


class RainService:

    @staticmethod
    def record(device_id: str, input_state: bool, is_active: bool) -> dict:
        entry = RainHistory(
            device_id=device_id,
            input=input_state,
            is_active=is_active,
        )
        db.session.add(entry)
        db.session.commit()
        db.session.refresh(entry)
        logger.info(
            "[RainService] recorded  device_id=%s  input=%s  is_active=%s",
            device_id, input_state, is_active,
        )
        return entry.to_dict()

    @staticmethod
    def get_latest(device_id: str) -> dict | None:
        entry = (
            RainHistory.query
            .filter_by(device_id=device_id)
            .order_by(RainHistory.recorded_at.desc())
            .first()
        )
        return entry.to_dict() if entry else None

    @staticmethod
    def get_history(device_id: str, limit: int = 50) -> list[dict]:
        entries = (
            RainHistory.query
            .filter_by(device_id=device_id)
            .order_by(RainHistory.recorded_at.desc())
            .limit(limit)
            .all()
        )
        return [e.to_dict() for e in entries]
