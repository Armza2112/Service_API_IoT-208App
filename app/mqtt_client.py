import json
import os
import queue
import threading
import logging

import paho.mqtt.client as mqtt

TOPIC_RELAY_CMD    = "iot208/{device_id}/relay/cmd"
TOPIC_RELAY_STATUS = "iot208/+/relay/status"
TOPIC_HEARTBEAT    = "iot208/+/heartbeat"
TOPIC_INPUT_STATUS = "iot208/+/input/status"

logger = logging.getLogger(__name__)


class MQTTManager:
    def __init__(self):
        self._client: mqtt.Client | None = None
        self._app    = None
        self._sse_clients: list[queue.Queue] = []
        self._lock   = threading.Lock()
        self._connected = False

    # ── Init ──────────────────────────────────────────────────────────────────

    def init_app(self, app):
        self._app = app
        if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
            return

        if self._client is not None:
            return

        cfg       = app.config
        broker    = cfg.get("MQTT_BROKER")
        port      = int(cfg.get("MQTT_PORT", 1883))
        base_id   = cfg.get("MQTT_CLIENT_ID", "iot208-backend")
        client_id = f"{base_id}-{os.getpid()}"
        transport = cfg.get("MQTT_TRANSPORT", "tcp")   # "tcp" | "websockets"
        ws_path   = cfg.get("MQTT_WS_PATH",   "/mqtt")

        addr = (
            f"ws://{broker}:{port}{ws_path}"
            if transport == "websockets"
            else f"mqtt://{broker}:{port}"
        )

        logger.info("=" * 60)
        logger.info("[MQTT] Initializing MQTT client")
        logger.info("[MQTT]   broker    : %s", broker)
        logger.info("[MQTT]   port      : %s", port)
        logger.info("[MQTT]   transport : %s", transport)
        logger.info("[MQTT]   client_id : %s", client_id)
        logger.info("[MQTT]   address   : %s", addr)
        logger.info("=" * 60)

        try:
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION1,
                client_id=client_id,
                transport=transport,
            )

            if transport == "websockets":
                client.ws_set_options(path=ws_path)

            if username := cfg.get("MQTT_USERNAME"):
                client.username_pw_set(username, cfg.get("MQTT_PASSWORD", ""))
                logger.info("[MQTT]   auth      : username=%s", username)

            client.on_connect    = self._on_connect
            client.on_disconnect = self._on_disconnect
            client.on_message    = self._on_message
            client.on_subscribe  = self._on_subscribe
            client.on_publish    = self._on_publish

            client.connect(broker, port, keepalive=60)
            self._client = client
            client.loop_start()

            logger.info("[MQTT] loop_start() — connecting to %s ...", addr)

        except Exception as exc:
            logger.error("[MQTT] Init error: %s", exc)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_connect(self, client, userdata, flags, rc, *args):
        if rc == 0:
            self._connected = True
            client.subscribe(TOPIC_RELAY_STATUS, qos=1)
            client.subscribe(TOPIC_HEARTBEAT,    qos=0)
            client.subscribe(TOPIC_INPUT_STATUS, qos=1)
            logger.info("=" * 60)
            logger.info("[MQTT] ✅ CONNECTED  rc=%s", rc)
            logger.info("[MQTT]   subscribed : %s  (qos=1)", TOPIC_RELAY_STATUS)
            logger.info("[MQTT]   subscribed : %s  (qos=0)", TOPIC_HEARTBEAT)
            logger.info("[MQTT]   subscribed : %s  (qos=1)", TOPIC_INPUT_STATUS)
            logger.info("=" * 60)
        else:
            self._connected = False
            _RC_MEANING = {
                1: "wrong protocol version",
                2: "invalid client id",
                3: "server unavailable",
                4: "bad username/password",
                5: "not authorised",
            }
            reason = _RC_MEANING.get(rc, "unknown")
            logger.error("[MQTT] ❌ CONNECT FAILED  rc=%s (%s)", rc, reason)

    def _on_disconnect(self, client, userdata, rc, *args):
        self._connected = False
        if rc == 0:
            logger.info("[MQTT] 🔌 Disconnected cleanly (rc=0)")
        else:
            logger.warning("[MQTT] ⚠️  Unexpected disconnect  rc=%s — will auto-reconnect", rc)

    def _on_subscribe(self, client, userdata, mid, granted_qos, *args):
        logger.info("[MQTT]   subscribe ack  mid=%s  granted_qos=%s", mid, granted_qos)

    def _on_publish(self, client, userdata, mid, *args):
        logger.debug("[MQTT]   publish ack  mid=%s", mid)

    def _on_message(self, client, userdata, msg: mqtt.MQTTMessage):
        """
          iot208/{device_id}/relay/status 
          iot208/{device_id}/heartbeat  
        """
        payload_str = msg.payload.decode("utf-8", errors="replace")

        logger.info("-" * 50)
        logger.info("[MQTT] ← RECEIVED")
        logger.info("[MQTT]   topic   : %s", msg.topic)
        logger.info("[MQTT]   payload : %s", payload_str)
        logger.info("[MQTT]   qos     : %s  retain=%s", msg.qos, bool(msg.retain))
        logger.info("-" * 50)

        parts = msg.topic.split("/")
        if len(parts) < 3:
            logger.warning("[MQTT] Unexpected topic format: %s", msg.topic)
            return

        device_id  = parts[1]
        event_type = parts[2]   # "relay" | "heartbeat" | "input"

        if event_type == "heartbeat":
            self._handle_heartbeat(device_id)
            return

        try:
            payload = json.loads(payload_str)
        except Exception as exc:
            logger.error("[MQTT] JSON parse error: %s  raw=%s", exc, payload_str)
            return

        if event_type == "input":
            # iot208/{device_id}/input/status  → Rain Sensor
            self._handle_input_status(device_id, payload, is_retained=bool(msg.retain))
            return

        # relay/status
        device_dict, relay1_on = self._update_db(device_id, payload)
        if device_dict:
            self._broadcast({"type": "relay_status", "device": device_dict})
            logger.info("[MQTT] relay_status → DB updated + SSE broadcast  device_id=%s", device_id)

            if relay1_on:
                model        = device_dict.get("model", "")
                model_serial = device_dict.get("model_serial", "")
                logger.warning("[MQTT] Relay1 turned ON → sending push notification  model=%s serial=%s",
                               model, model_serial)
                self._notify_relay1_on(device_id, model_serial)
        else:
            logger.warning("[MQTT] relay_status → DB update skipped  device_id=%s", device_id)

    # ── Business logic ────────────────────────────────────────────────────────

    def _handle_heartbeat(self, device_id: str):
        try:
            with self._app.app_context():
                from app.services.device_service import DeviceService
                result = DeviceService.update_heartbeat(device_id)
                if result:
                    self._broadcast({"type": "heartbeat", "device": result})
                    logger.info("[MQTT] heartbeat → device_id=%s  is_active=True  last_seen updated", device_id)
                else:
                    logger.warning("[MQTT] heartbeat → device_id not found in DB: %s", device_id)
        except Exception as exc:
            logger.error("[MQTT] heartbeat DB error: %s", exc)

    def _handle_input_status(self, device_id: str, payload: dict, is_retained: bool = False):
        """
        iot208/{device_id}/input/status  payload: {"input": bool, "is_active": bool}
        """
        input_state = bool(payload.get("input", False))
        is_active   = bool(payload.get("is_active", True))

        try:
            with self._app.app_context():
                from app.services.rain_service import RainService
                entry = RainService.record(device_id, input_state, is_active)
                self._broadcast({"type": "rain_status", "rain": entry})
                logger.info(
                    "[MQTT] rain_status → recorded + SSE broadcast  device_id=%s  input=%s  retained=%s",
                    device_id, input_state, is_retained,
                )
        except Exception as exc:
            logger.error("[MQTT] _handle_input_status DB error: %s", exc)
            return

        if is_retained:
            logger.warning("[MQTT] input/status RETAINED — skip FCM  device_id=%s  input=%s", device_id, input_state)
            return

        if input_state:
            logger.warning("[MQTT] Rain input=True (fresh) → sending FCM  device_id=%s", device_id)
            self._notify_rain(device_id)

    def _update_db(self, device_id: str, payload: dict) -> tuple[dict | None, bool]:
        """
        Returns: (device_dict, relay1_turned_on)
          relay1_turned_on = True เมื่อ relay[0] เปลี่ยนจาก False → True เท่านั้น
        """
        if not self._app:
            return None, False
        try:
            with self._app.app_context():
                from app.entities.device_profile_entity import DeviceProfile
                from app.extensions import db

                device = DeviceProfile.query.filter_by(device_id=device_id).first()
                if not device:
                    all_ids = [d.device_id for d in DeviceProfile.query.all()]
                    logger.warning("[MQTT] device_id not found: '%s'", device_id)
                    logger.warning("[MQTT] registered device_ids in DB: %s", all_ids)
                    return None, False

                relay1_turned_on = False

                if "relay" in payload and isinstance(payload["relay"], list) and len(payload["relay"]) >= 4:
                    new_relay = [bool(v) for v in payload["relay"][:4]]

                    old_relay1 = bool((device.status_relay or [False])[0])
                    new_relay1 = new_relay[0]
                    logger.warning("[MQTT]   relay[0] old=%s new=%s", old_relay1, new_relay1)
                    if not old_relay1 and new_relay1:
                        relay1_turned_on = True
                        logger.warning("[MQTT]   relay[0] transitioned OFF → ON → FCM will fire")

                    device.status_relay = new_relay
                    logger.info("[MQTT]   relay state → %s", device.status_relay)

                if "is_active" in payload:
                    device.is_active = bool(payload["is_active"])
                    logger.info("[MQTT]   is_active  → %s", device.is_active)

                db.session.commit()
                db.session.refresh(device)
                return device.to_dict(), relay1_turned_on

        except Exception as exc:
            logger.error("[MQTT] DB update error: %s", exc)
            return None, False

    def _notify_relay1_on(self, device_id: str, model_serial: str = ""):
        """ใช้ model_serial เป็นหลัก — ดูคำหลัง IoT เหมือน frontend"""
        s    = model_serial.lower()
        core = s[3:] if s.startswith("iot") else s   # IoTWaterPlantX4 → waterplantx4

        if core.startswith("rainsensor") or "rain" in core:
            title = "💧 เปิดวาล์วน้ำแล้ว"
            body  = "เปิดวาล์วปล่อยน้ำออกจากถังแล้ว"
        elif core.startswith("controller"):
            title = "⚡ เปิด Controller แล้ว"
            body  = f"อุปกรณ์ {model_serial} เปิด Relay 1 แล้ว"
        elif core.startswith("waterplant") or core.startswith("water"):
            title = "🌿 เริ่มรดน้ำแล้ว"
            body  = "ระบบรดน้ำอัตโนมัติเริ่มทำงานแล้ว"
        else:
            title = "⚡ Relay เปิดแล้ว"
            body  = f"อุปกรณ์ {model_serial} เปิด Relay 1 แล้ว"

        try:
            from app.services.fcm_service import send_push_to_all_members
            sent = send_push_to_all_members(
                app       = self._app,
                title     = title,
                body      = body,
                data      = {"type": "relay1_on", "model_serial": model_serial},
                dedup_key = f"relay1_on:{device_id}",
            )
            logger.warning("[MQTT] Push notification sent to %d device(s)  title=%r", sent, title)
        except Exception as exc:
            logger.error("[MQTT] _notify_relay1_on error: %s", exc)

    def _notify_rain(self, device_id: str):
        try:
            from app.services.fcm_service import send_push_to_all_members
            sent = send_push_to_all_members(
                app       = self._app,
                title     = "🌧️ ฝนกำลังตก",
                body      = "เซนเซอร์ตรวจจับว่าฝนกำลังตกอยู่",
                data      = {"type": "rain_detected", "device_id": device_id},
                dedup_key = f"rain:{device_id}",
            )
            logger.warning("[MQTT] Rain push sent to %d device(s)", sent)
        except Exception as exc:
            logger.error("[MQTT] _notify_rain error: %s", exc)

    # -- Publish ------------------------------------------------------------------

    def publish_relay_command(self, device_id: str, channel: int, value: bool) -> bool:
        """
        topic  : iot208/{device_id}/relay/cmd
        payload: {"channel": 0, "value": true}
        """
        if not self._client or not self._connected:
            logger.warning("[MQTT] -> PUBLISH FAILED -- not connected  device_id=%s ch=%s val=%s",
                           device_id, channel, value)
            return False

        topic   = TOPIC_RELAY_CMD.format(device_id=device_id)
        payload = json.dumps({"channel": channel, "value": value})
        result  = self._client.publish(topic, payload, qos=1)
        ok      = result.rc == mqtt.MQTT_ERR_SUCCESS

        logger.info("[MQTT] -> PUBLISH")
        logger.info("[MQTT]   topic   : %s", topic)
        logger.info("[MQTT]   payload : %s", payload)
        logger.info("[MQTT]   result  : %s", "OK" if ok else f"FAIL rc={result.rc}")

        return ok

    # -- SSE ----------------------------------------------------------------------

    def _broadcast(self, data: dict):
        with self._lock:
            dead = []
            for q in self._sse_clients:
                try:
                    q.put_nowait(data)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                self._sse_clients.remove(q)
            if self._sse_clients:
                logger.debug("[MQTT] SSE broadcast -> %d client(s)  type=%s",
                             len(self._sse_clients), data.get("type"))

    def subscribe_sse(self) -> queue.Queue:
        q = queue.Queue(maxsize=50)
        with self._lock:
            self._sse_clients.append(q)
        logger.debug("[MQTT] SSE client connected  total=%d", len(self._sse_clients))
        return q

    def unsubscribe_sse(self, q: queue.Queue):
        with self._lock:
            if q in self._sse_clients:
                self._sse_clients.remove(q)
        logger.debug("[MQTT] SSE client disconnected  total=%d", len(self._sse_clients))

    @property
    def is_connected(self) -> bool:
        return self._connected


mqtt_manager = MQTTManager()
