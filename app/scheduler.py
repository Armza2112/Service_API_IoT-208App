"""
Automation Scheduler -- APScheduler singleton
Job ID convention:
  "auto_<automation_id>"          -- scheduled relay trigger
  "float_off_<automation_id>"     -- post-trigger float-sensor monitor
  "verify_off_<device_id>_<ch>"   -- relay-off safety re-check after 5 min
  "check_pump_overtime"           -- pump-on-too-long monitor (every 2 min)
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

# Track which relay-on sessions have already been notified (prevents repeat alerts)
_notified_pump_sessions: set[str] = set()

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

if TYPE_CHECKING:
    from flask import Flask
    from app.entities.automation_entity import Automation

logger = logging.getLogger(__name__)

_DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _days_to_cron(days: list[int]) -> str:
    return ",".join(_DAY_NAMES[d] for d in sorted(set(days)))


def _make_job_id(automation_id: int) -> str:
    return f"auto_{automation_id}"


def _run_relay(
    app,
    device_id:        str,
    channel:          int,
    action:           bool,
    automation_id:    int,
    automation_name:  str       = "",
    duration_minutes: int | None = None,
    skip_if_raining:  bool      = False,
    until_float_off:  bool      = False,
):
    """
    APScheduler callback -- runs inside Flask app context.

    Rain-guard logic:
      If skip_if_raining=True we query the most recent RainHistory row
      (any device — no hardcoded env-var UUID). If input=True → skip + FCM.

    Float-off logic:
      If until_float_off=True and action=True, after sending relay ON we
      kick off a 30-second polling job (_check_float_and_off) that watches
      RainHistory for device_id. The moment input=False is recorded the job
      sends relay OFF and removes itself.
    """
    with app.app_context():
        from app.mqtt_client import mqtt_manager

        logger.info(
            "[Scheduler] Firing automation %s (%r) -> device=%s ch=%s action=%s "
            "skip_rain=%s until_float_off=%s",
            automation_id, automation_name, device_id, channel, action,
            skip_if_raining, until_float_off,
        )

        # ── Rain guard ────────────────────────────────────────────────────────
        if skip_if_raining:
            try:
                from app.entities.rain_history_entity import RainHistory
                # Query the most recent reading across ALL rain-sensor devices.
                # No hardcoded device_id / env-var needed — works even after
                # re-registering hardware in production.
                latest = (
                    RainHistory.query
                    .order_by(RainHistory.recorded_at.desc())
                    .first()
                )
                if latest and latest.input is True:
                    scene_label = automation_name or f"Scene #{automation_id}"
                    logger.info("[Scheduler] SKIPPED %s -- rain detected (device=%s)",
                                automation_id, latest.device_id)
                    try:
                        from app.services.fcm_service import send_push_to_all_members
                        send_push_to_all_members(
                            app=app,
                            title="🌧️ ข้ามการรดน้ำ",
                            body=f'ตรวจพบฝนตก — "{scene_label}" ถูกข้ามไป',
                            data={
                                "type": "scene_skipped_rain",
                                "automation_id": str(automation_id),
                            },
                        )
                    except Exception as fcm_exc:
                        logger.warning("[Scheduler] FCM skip-notify error: %s", fcm_exc)
                    return
            except Exception as rain_exc:
                # fail-open: if rain check breaks, proceed with relay
                logger.warning("[Scheduler] Rain check error -- proceeding: %s", rain_exc)

        # ── Fire relay command ────────────────────────────────────────────────
        try:
            published = mqtt_manager.publish_relay_command(device_id, channel, action)
            if not published:
                logger.warning("[Scheduler] MQTT offline -- automation %s queued", automation_id)
        except Exception as exc:
            logger.error("[Scheduler] automation %s error: %s", automation_id, exc)
            return

        # ── Relay-off safety verify (5 min after close command) ──────────────
        # If relay is still ON in DB after 5 min → re-send close command once
        if not action:
            try:
                verify_id = f"verify_off_{device_id}_{channel}"
                scheduler_manager._scheduler.add_job(
                    func=_verify_relay_off,
                    trigger="date",
                    run_date=datetime.now() + timedelta(minutes=5),
                    id=verify_id,
                    replace_existing=True,
                    args=[app, device_id, channel, verify_id],
                )
                logger.info(
                    "[Scheduler] Relay-off verify scheduled in 5 min  device=%s ch=%s",
                    device_id, channel,
                )
            except Exception as exc:
                logger.warning("[Scheduler] Could not schedule verify-off: %s", exc)

        # ── Duration auto-off ─────────────────────────────────────────────────
        # When action=ON + duration_minutes set → schedule one-shot relay OFF
        if action and duration_minutes:
            try:
                dur_job_id = f"dur_off_{automation_id}"
                scheduler_manager._scheduler.add_job(
                    func=_duration_off,
                    trigger="date",
                    run_date=datetime.now() + timedelta(minutes=duration_minutes),
                    id=dur_job_id,
                    replace_existing=True,
                    args=[app, device_id, channel, automation_id, dur_job_id],
                )
                logger.info(
                    "[Scheduler] Duration auto-off in %d min  device=%s ch=%s auto=%s",
                    duration_minutes, device_id, channel, automation_id,
                )
            except Exception as exc:
                logger.warning("[Scheduler] Could not schedule duration-off: %s", exc)

        # ── Float-off monitor ─────────────────────────────────────────────────
        # Only when: turning ON + until_float_off flag set
        if action and until_float_off:
            try:
                monitor_id = f"float_off_{automation_id}"
                scheduler_manager._scheduler.add_job(
                    func=_check_float_and_off,
                    trigger="interval",
                    seconds=30,
                    id=monitor_id,
                    replace_existing=True,
                    args=[app, device_id, channel, automation_id, monitor_id],
                )
                logger.info("[Scheduler] Float monitor started: %s (device=%s ch=%s)",
                            monitor_id, device_id, channel)
            except Exception as exc:
                logger.warning("[Scheduler] Could not start float monitor: %s", exc)


def _verify_relay_off(app, device_id: str, channel: int, job_id: str):
    """
    One-shot job fired 5 minutes after a relay-OFF command was sent.
    Reads relay state from DB; if still ON → re-send close command.
    """
    with app.app_context():
        try:
            from app.entities.device_profile_entity import DeviceProfile
            from app.mqtt_client import mqtt_manager

            device = DeviceProfile.query.filter_by(device_id=device_id).first()
            if not device:
                logger.warning("[VerifyOff] device not found: %s", device_id)
                return

            relay_state = device.status_relay or []
            still_on = bool(relay_state[channel]) if channel < len(relay_state) else False

            if still_on:
                logger.warning(
                    "[VerifyOff] relay[%d] still ON after 5 min -- re-sending OFF  device=%s",
                    channel, device_id,
                )
                mqtt_manager.publish_relay_command(device_id, channel, False)
            else:
                logger.info(
                    "[VerifyOff] relay[%d] confirmed OFF  device=%s",
                    channel, device_id,
                )
        except Exception as exc:
            logger.warning("[VerifyOff] Error: %s", exc)
        finally:
            try:
                scheduler_manager._scheduler.remove_job(job_id)
            except Exception:
                pass


def _duration_off(app, device_id: str, channel: int, automation_id: int, job_id: str):
    """One-shot job: fires relay OFF after duration_minutes has elapsed."""
    with app.app_context():
        try:
            from app.mqtt_client import mqtt_manager
            mqtt_manager.publish_relay_command(device_id, channel, False)
            logger.info(
                "[DurationOff] relay OFF sent  auto=%s device=%s ch=%s",
                automation_id, device_id, channel,
            )
        except Exception as exc:
            logger.warning("[DurationOff] Error: %s", exc)
        finally:
            try:
                scheduler_manager._scheduler.remove_job(job_id)
            except Exception:
                pass


def _check_float_and_off(
    app,
    device_id:     str,
    channel:       int,
    automation_id: int,
    job_id:        str,
):
    """
    Runs every 30 s after a relay-ON fired with until_float_off=True.
    Reads the latest RainHistory row for device_id.

    Logic:
      input=True  → ลูกลอยไม่เจอน้ำ (น้ำหมดถัง) → ปิด relay
      input=False → ลูกลอยยังอยู่ในน้ำ (มีน้ำอยู่)  → รอต่อ
    """
    with app.app_context():
        try:
            from app.entities.rain_history_entity import RainHistory
            from app.mqtt_client import mqtt_manager

            latest = (
                RainHistory.query
                .filter_by(device_id=device_id)
                .order_by(RainHistory.recorded_at.desc())
                .first()
            )
            if latest is None:
                logger.debug("[FloatMonitor] No rain_history yet for device=%s", device_id)
                return

            logger.debug(
                "[FloatMonitor] auto=%s device=%s input=%s recorded_at=%s",
                automation_id, device_id, latest.input, latest.recorded_at,
            )

            if latest.input is True:
                mqtt_manager.publish_relay_command(device_id, channel, False)
                logger.info(
                    "[FloatMonitor] น้ำหมด (input=True) → relay OFF  auto=%s device=%s ch=%s",
                    automation_id, device_id, channel,
                )
                # Remove this monitoring job
                try:
                    scheduler_manager._scheduler.remove_job(job_id)
                    logger.info("[FloatMonitor] Monitor job removed: %s", job_id)
                except Exception:
                    pass

        except Exception as exc:
            logger.warning("[FloatMonitor] Error in float check (auto=%s): %s", automation_id, exc)


def _check_pump_overtime(app):
    """
    Periodic job (every 2 min): ถ้า relay ของปั้มน้ำเปิดมาเกิน 11 นาที → FCM
    dedup ต่อ on-session (relay_history.id) ไม่แจ้งซ้ำสำหรับ session เดิม
    """
    global _notified_pump_sessions
    THRESHOLD = timedelta(minutes=11)

    with app.app_context():
        try:
            from app.entities.device_profile_entity import DeviceProfile
            from app.entities.relay_history_entity import RelayHistory
            from app.services.fcm_service import send_push_to_all_members

            now = datetime.now(timezone.utc)

            for device in DeviceProfile.query.filter_by(is_active=True).all():
                ms   = device.model_serial.lower()
                core = ms[3:] if ms.startswith("iot") else ms

                # เฉพาะอุปกรณ์น้ำ — ข้ามประตูและ rain sensor
                if core.startswith("controllerdoor") or core.startswith("rainsensor"):
                    continue

                relay_states = device.status_relay or []
                for ch, is_on in enumerate(relay_states):
                    if not is_on:
                        continue

                    # หา ON event ล่าสุดของ channel นี้
                    last_on = (
                        RelayHistory.query
                        .filter_by(device_id=device.device_id, channel=ch, value=True)
                        .order_by(RelayHistory.recorded_at.desc())
                        .first()
                    )
                    if not last_on:
                        continue

                    recorded_at = last_on.recorded_at
                    if recorded_at.tzinfo is None:
                        recorded_at = recorded_at.replace(tzinfo=timezone.utc)

                    elapsed = now - recorded_at
                    if elapsed < THRESHOLD:
                        continue

                    # dedup ต่อ session (unique per history row id)
                    session_key = f"pump_overtime:{device.device_id}:{ch}:{last_on.id}"
                    if session_key in _notified_pump_sessions:
                        continue
                    _notified_pump_sessions.add(session_key)

                    elapsed_min = int(elapsed.total_seconds() // 60)
                    ch_label    = f"CH{ch + 1}"
                    label       = device.model or device.model_serial

                    send_push_to_all_members(
                        app=app,
                        title="⚠️ ปั้มน้ำเปิดนานเกินไป",
                        body=f"{label} ({ch_label}) เปิดมาแล้ว {elapsed_min} นาที",
                        data={
                            "type":      "pump_overtime",
                            "device_id": device.device_id,
                            "channel":   str(ch),
                        },
                        dedup_key=session_key,
                    )
                    logger.warning(
                        "[PumpOvertime] Notified device=%s ch=%s elapsed=%dm",
                        device.device_id, ch, elapsed_min,
                    )

        except Exception as exc:
            logger.error("[PumpOvertime] Error: %s", exc)


class SchedulerManager:
    def __init__(self):
        self._scheduler = BackgroundScheduler(timezone="Asia/Bangkok")
        self._app = None

    def init_app(self, app: "Flask") -> None:
        self._app = app

        with app.app_context():
            from app.services.automation_service import AutomationService
            enabled = AutomationService.list_enabled()
            for auto in enabled:
                self._schedule(auto)

        self._scheduler.add_job(
            func=self._check_stale_devices,
            trigger="interval",
            minutes=15,
            id="check_stale_devices",
            replace_existing=True,
        )

        self._scheduler.add_job(
            func=_check_pump_overtime,
            trigger="interval",
            minutes=2,
            id="check_pump_overtime",
            replace_existing=True,
            args=[app],
        )

        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("[Scheduler] Started with %d automation job(s)", len(enabled))

    def _schedule(self, auto: "Automation") -> None:
        job_id = _make_job_id(auto.id)
        h, m   = auto.trigger_time.split(":")

        trigger = CronTrigger(
            day_of_week=_days_to_cron(auto.trigger_days),
            hour=int(h),
            minute=int(m),
            second=0,
            timezone="Asia/Bangkok",
        )

        self._scheduler.add_job(
            func=_run_relay,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            args=[
                self._app,
                auto.device_id,
                auto.channel,
                auto.action,
                auto.id,
                auto.name,
                getattr(auto, "duration_minutes", None),
                auto.skip_if_raining,
                getattr(auto, "until_float_off", False),
            ],
        )
        logger.debug(
            "[Scheduler] Scheduled %s at %s days=%s dur=%s skip_rain=%s until_float_off=%s",
            job_id, auto.trigger_time, auto.trigger_days,
            getattr(auto, "duration_minutes", None),
            auto.skip_if_raining, getattr(auto, "until_float_off", False),
        )

    def _check_stale_devices(self):
        with self._app.app_context():
            from app.services.device_service import DeviceService
            from app.mqtt_client import mqtt_manager
            count = DeviceService.mark_stale_offline(timeout_minutes=15)
            if count:
                logger.info("[Scheduler] Marked %d device(s) offline", count)
                try:
                    from app.entities.device_profile_entity import DeviceProfile
                    for d in DeviceProfile.query.filter_by(is_active=False).all():
                        mqtt_manager._broadcast({"type": "heartbeat", "device": d.to_dict()})
                except Exception:
                    pass

    def add_job(self, auto: "Automation") -> None:
        if not auto.is_enabled:
            return
        self._schedule(auto)

    def reschedule_job(self, auto: "Automation") -> None:
        self.remove_job(auto.id)
        if auto.is_enabled:
            self._schedule(auto)

    def pause_job(self, automation_id: int) -> None:
        try:
            self._scheduler.pause_job(_make_job_id(automation_id))
        except Exception:
            pass

    def resume_job(self, automation_id: int) -> None:
        try:
            self._scheduler.resume_job(_make_job_id(automation_id))
        except Exception:
            with self._app.app_context():
                from app.services.automation_service import AutomationService
                auto = AutomationService.get_by_id(automation_id)
                if auto and auto.is_enabled:
                    self._schedule(auto)

    def remove_job(self, automation_id: int) -> None:
        try:
            self._scheduler.remove_job(_make_job_id(automation_id))
        except Exception:
            pass

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)


scheduler_manager = SchedulerManager()
