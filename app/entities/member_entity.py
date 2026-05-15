from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class MbMem(db.Model):
    __tablename__ = "mb_mem"

    # ── Primary Key ───────────────────────────────────────────
    mem_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Auto-increment primary key",
    )

    # ── Personal Info ─────────────────────────────────────────
    mem_firstname: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="ชื่อจริง",
    )

    mem_lastname: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="นามสกุล",
    )

    mem_email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="อีเมล (unique)",
    )

    mem_phone: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="เบอร์โทรศัพท์",
    )

    # ── FCM Token ─────────────────────────────────────────────
    mem_fcm: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="Firebase Cloud Messaging Token",
    )

    # ── Auth ──────────────────────────────────────────────────
    mem_username: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="ชื่อผู้ใช้ (unique)",
    )

    mem_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="รหัสผ่าน (hashed with werkzeug)",
    )

    # ── Timestamps ────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Methods ───────────────────────────────────────────────
    def to_dict(self, include_password: bool = False) -> dict:
        data = {
            "mem_id": self.mem_id,
            "mem_firstname": self.mem_firstname,
            "mem_lastname": self.mem_lastname,
            "mem_email": self.mem_email,
            "mem_phone": self.mem_phone,
            "mem_fcm": self.mem_fcm,
            "mem_username": self.mem_username,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_password:
            data["mem_password"] = self.mem_password
        return data

    def __repr__(self) -> str:
        return f"<MbMem mem_id={self.mem_id} username={self.mem_username} email={self.mem_email}>"
