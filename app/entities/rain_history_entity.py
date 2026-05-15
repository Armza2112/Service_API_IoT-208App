from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class RainHistory(db.Model):
    __tablename__ = "rain_history"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    device_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Device UUID ของ rain sensor",
    )

    input: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        comment="True = ฝนตก, False = ไม่มีฝน",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="สถานะออนไลน์ของอุปกรณ์ขณะส่งข้อมูล",
    )

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
        comment="เวลาที่บันทึก (UTC)",
    )

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "device_id":   self.device_id,
            "input":       self.input,
            "is_active":   self.is_active,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
        }

    def __repr__(self) -> str:
        status = "ฝนตก" if self.input else "ไม่มีฝน"
        return f"<RainHistory device_id={self.device_id} status={status} at={self.recorded_at}>"
