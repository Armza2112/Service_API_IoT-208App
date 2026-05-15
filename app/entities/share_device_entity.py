from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class ShareDevice(db.Model):
    __tablename__ = "share_device"

    __table_args__ = (
        UniqueConstraint("owner_mem_id", "shared_mem_id", "device_id",
                         name="uq_share_device"),
    )

    # ── Primary Key ───────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    owner_mem_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("mb_mem.mem_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="mem_id ของเจ้าของอุปกรณ์ที่แชร์",
    )

    shared_mem_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("mb_mem.mem_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="mem_id ของคนที่รับการแชร์",
    )

    device_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("device_profiles.device_id", ondelete="CASCADE"),
        nullable=False,
        comment="device_id ที่แชร์",
    )

    # ── Timestamp ─────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def to_dict(self) -> dict:
        return {
            "id":            self.id,
            "owner_mem_id":  self.owner_mem_id,
            "shared_mem_id": self.shared_mem_id,
            "device_id":     self.device_id,
            "created_at":    self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return (f"<ShareDevice id={self.id} owner={self.owner_mem_id} "
                f"shared={self.shared_mem_id} device={self.device_id}>")
