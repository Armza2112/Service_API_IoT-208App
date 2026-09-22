from datetime import datetime
from typing import List, Optional

from sqlalchemy import String, Boolean, DateTime, Integer, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class DeviceProfile(db.Model):
    __tablename__ = "device_profiles"

    # ── Primary Key ───────────────────────────────────────────
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Auto-increment primary key",
    )

    # ── Identity Columns ──────────────────────────────────────
    device_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="Device UUID",
    )

    mac_address: Mapped[str] = mapped_column(
        String(17),
        unique=True,
        nullable=False,
        index=True,
        comment="MAC Address XX:XX:XX:XX:XX:XX",
    )

    model: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="IoT Plant Water",
    )

    model_serial: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="208xxxxxx",
    )

    # ── Role ─────────────────────────────────────────────────
    role: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        default=None,
        comment="UI role: water_outside | water_inside | door | None",
    )

    # ── Relay Status ──────────────────────────────────────────
    status_relay: Mapped[List[bool]] = mapped_column(
        ARRAY(Boolean),
        nullable=False,
        default=lambda: [False, False, False, False],
        server_default="{false,false,false,false}",
        comment="Relay state [ch0, ch1, ch2, ch3] True=ON False=OFF",
    )

    # ── Status ────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment="True=online  False=offline (updated by heartbeat)",
    )

    # ── Heartbeat ─────────────────────────────────────────────
    last_seen: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Timestamp of last heartbeat from device",
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
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "device_id": self.device_id,
            "mac_address": self.mac_address,
            "model": self.model,
            "model_serial": self.model_serial,
            "role": self.role,
            "status_relay": self.status_relay,
            "is_active":  self.is_active,
            "last_seen":  self.last_seen.isoformat() if self.last_seen else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        relay = self.status_relay
        return f"<DeviceProfile device_id={self.device_id} mac={self.mac_address} relay={relay}>"
