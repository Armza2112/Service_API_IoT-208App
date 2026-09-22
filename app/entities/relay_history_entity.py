from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class RelayHistory(db.Model):
    __tablename__ = "relay_history"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    device_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Device UUID",
    )

    device_name: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        comment="Snapshot ของชื่อ device ขณะบันทึก",
    )

    channel: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Relay channel 0-3",
    )

    value: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        comment="True=เปิด  False=ปิด",
    )

    source: Mapped[Optional[str]] = mapped_column(
        String(16),
        nullable=True,
        comment="mqtt | api",
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
            "device_name": self.device_name,
            "channel":     self.channel,
            "value":       self.value,
            "source":      self.source,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
        }
