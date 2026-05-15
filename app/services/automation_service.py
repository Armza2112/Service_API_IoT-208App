from typing import List, Optional

from app.extensions import db
from app.entities.automation_entity import Automation


class AutomationService:

    @staticmethod
    def list_all() -> List[Automation]:
        return (
            Automation.query
            .order_by(Automation.created_at.desc())
            .all()
        )

    @staticmethod
    def get_by_id(automation_id: int) -> Optional[Automation]:
        return Automation.query.get(automation_id)

    @staticmethod
    def create(
        mem_id:           int,
        name:             str,
        device_id:        str,
        channel:          int,
        action:           bool,
        trigger_time:     str,
        trigger_days:     List[int],
        skip_if_raining:  bool = False,
        until_float_off:  bool = False,
    ) -> Automation:
        auto = Automation(
            name=name.strip(),
            device_id=device_id,
            channel=channel,
            action=action,
            trigger_time=trigger_time,
            trigger_days=trigger_days,
            is_enabled=True,
            skip_if_raining=skip_if_raining,
            until_float_off=until_float_off,
            created_by=mem_id,
        )
        db.session.add(auto)
        db.session.commit()
        db.session.refresh(auto)
        return auto

    @staticmethod
    def update(automation_id: int, **kwargs) -> Automation:
        auto = Automation.query.get(automation_id)
        if not auto:
            raise ValueError("Automation not found")

        allowed = {"name", "device_id", "channel", "action", "trigger_time", "trigger_days"}
        for key, val in kwargs.items():
            if key in allowed and val is not None:
                setattr(auto, key, val)

        # bool fields: handle separately (can be False — don't skip on falsy check)
        if "skip_if_raining" in kwargs and isinstance(kwargs["skip_if_raining"], bool):
            auto.skip_if_raining = kwargs["skip_if_raining"]
        if "until_float_off" in kwargs and isinstance(kwargs["until_float_off"], bool):
            auto.until_float_off = kwargs["until_float_off"]

        db.session.commit()
        db.session.refresh(auto)
        return auto

    @staticmethod
    def toggle(automation_id: int) -> Automation:
        auto = Automation.query.get(automation_id)
        if not auto:
            raise ValueError("Automation not found")
        auto.is_enabled = not auto.is_enabled
        db.session.commit()
        db.session.refresh(auto)
        return auto

    @staticmethod
    def delete(automation_id: int) -> None:
        auto = Automation.query.get(automation_id)
        if not auto:
            raise ValueError("Automation not found")
        db.session.delete(auto)
        db.session.commit()

    @staticmethod
    def list_enabled() -> List[Automation]:
        return Automation.query.filter_by(is_enabled=True).all()
