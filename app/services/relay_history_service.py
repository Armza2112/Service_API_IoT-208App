import logging
from typing import Optional

from app.extensions import db
from app.entities.relay_history_entity import RelayHistory

logger = logging.getLogger(__name__)


class RelayHistoryService:

    @staticmethod
    def record(
        device_id: str,
        device_name: Optional[str],
        channel: int,
        value: bool,
        source: str = "mqtt",
    ) -> None:
        """บันทึก relay event — ไม่ throw ถ้า DB error"""
        try:
            entry = RelayHistory(
                device_id=device_id,
                device_name=device_name,
                channel=channel,
                value=value,
                source=source,
            )
            db.session.add(entry)
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.error("[RelayHistory] record error: %s", exc)

    @staticmethod
    def list_history(
        page: int = 1,
        per_page: int = 50,
        device_id: Optional[str] = None,
    ) -> dict:
        query = RelayHistory.query.order_by(RelayHistory.recorded_at.desc())
        if device_id:
            query = query.filter(RelayHistory.device_id == device_id)

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return {
            "history": [h.to_dict() for h in pagination.items],
            "pagination": {
                "total":        pagination.total,
                "pages":        pagination.pages,
                "current_page": pagination.page,
                "per_page":     pagination.per_page,
                "has_next":     pagination.has_next,
                "has_prev":     pagination.has_prev,
            },
        }
