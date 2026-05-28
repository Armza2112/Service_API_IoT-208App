from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class Automation(db.Model):
    __tablename__ = "automations"

    # Primary Key
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Auto-increment primary key",
    )

    # Scene info
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Scene display name",
    )

    # Target device
    device_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="UUID of the target DeviceProfile",
    )

    channel: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Relay channel 0-3",
    )

    action: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        comment="True=ON  False=OFF",
    )

    # Schedule
    trigger_time: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        comment="HH:MM  e.g. 07:30",
    )

    # Array of weekday integers: 0=Mon, 6=Sun
    trigger_days: Mapped[List[int]] = mapped_column(
        ARRAY(Integer),
        nullable=False,
        server_default="{0,1,2,3,4,5,6}",
        comment="Weekdays to fire: 0=Mon to 6=Sun",
    )

    # State
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="True=active  False=paused",
    )

    # Rain condition
    # True: scheduler checks rain sensor before firing relay command
    # If rain detected (rain_history.input=True) -> skip + push notification
    skip_if_raining: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="True=skip scene if rain sensor detects rain",
    )

    # Duration: auto-OFF after N minutes (WaterPlant only, action=ON)
    duration_minutes: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=None,
        comment="Auto-off after N minutes (None = no auto-off)",
    )

    # Float-off condition (Rain Sensor board only)
    # True: after relay ON fires, scheduler polls rain_history.input for this
    # device every 30 s and sends relay OFF once input=False (tank full / float triggered)
    until_float_off: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="True=keep relay ON until float sensor input=False",
    )

    # Owner
    created_by: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
        comment="mem_id of the member who created this",
    )

    # Timestamps
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

    def to_dict(self) -> dict:
        return {
            "id":              self.id,
            "name":            self.name,
            "device_id":       self.device_id,
            "channel":         self.channel,
            "action":          self.action,
            "trigger_time":    self.trigger_time,
            "trigger_days":    self.trigger_days,
            "is_enabled":        self.is_enabled,
            "duration_minutes":  self.duration_minutes,
            "skip_if_raining":   self.skip_if_raining,
            "until_float_off":   self.until_float_off,
            "created_by":      self.created_by,
            "created_at":      self.created_at.isoformat() if self.created_at else None,
            "updated_at":      self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<Automation id={self.id} name={self.name!r} "
            f"device={self.device_id} ch={self.channel} "
            f"action={'ON' if self.action else 'OFF'} "
            f"at={self.trigger_time} days={self.trigger_days} "
            f"skip_rain={self.skip_if_raining}>"
        )
