import json
import logging
import os
import time

logger = logging.getLogger(__name__)

_initialized = False

# ── Dedup ─────────────────────────────────────────────────────────────────────
# ป้องกันส่ง push notification ซ้ำภายใน 30 วินาที per key
_dedup_cache: dict[str, float] = {}
_DEDUP_TTL = 30  # seconds


def _check_dedup(key: str) -> bool:
    """Return True ถ้าควรส่ง, False ถ้าซ้ำเกินไป"""
    now = time.monotonic()
    last = _dedup_cache.get(key, 0.0)
    if now - last < _DEDUP_TTL:
        logger.warning("[FCM] Dedup suppressed: key=%r  (%.1fs ago)", key, now - last)
        return False
    _dedup_cache[key] = now
    return True


def _init_firebase() -> bool:
    """Initialize Firebase Admin SDK (idempotent)."""
    global _initialized
    if _initialized:
        return True

    try:
        import firebase_admin
        from firebase_admin import credentials

        if firebase_admin._apps:
            _initialized = True
            return True

        sa_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "").strip()
        sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()

        if sa_path and os.path.exists(sa_path):
            cred = credentials.Certificate(sa_path)
            logger.info("[FCM] Using service account file: %s", sa_path)
        elif sa_json:
            cred = credentials.Certificate(json.loads(sa_json))
            logger.info("[FCM] Using service account from env JSON")
        else:
            logger.error(
                "[FCM] No Firebase credentials found. "
                "Set FIREBASE_SERVICE_ACCOUNT_PATH or FIREBASE_SERVICE_ACCOUNT_JSON"
            )
            return False

        firebase_admin.initialize_app(cred)
        _initialized = True
        logger.warning("[FCM] Firebase Admin SDK initialized ✓")
        return True

    except Exception as exc:
        logger.error("[FCM] Firebase Admin init error: %s", exc)
        return False


def send_push_to_tokens(
    tokens: list[str],
    title: str,
    body: str,
    data: dict | None = None,
) -> int:
    tokens = [t for t in (tokens or []) if t and t.strip()]
    if not tokens:
        logger.warning("[FCM] send_push: no valid tokens")
        return 0

    if not _init_firebase():
        return 0

    try:
        from firebase_admin import messaging

        payload_data = {k: str(v) for k, v in (data or {}).items()}

        message = messaging.MulticastMessage(
            data=payload_data,
            tokens=tokens,
            android=messaging.AndroidConfig(priority="high"),
            # webpush: ใส่ notification ให้ Firebase SDK แสดงเอง
            # service worker จะไม่ showNotification ซ้ำอีก
            webpush=messaging.WebpushConfig(
                notification=messaging.WebpushNotification(
                    title=title,
                    body=body,
                    icon="/icons/icon-192x192.png",
                ),
                fcm_options=messaging.WebpushFCMOptions(
                    link="https://baan208-iot.biz/dashboard",
                ),
            ),
        )

        response = messaging.send_each_for_multicast(message)
        logger.warning(
            "[FCM] Sent %d/%d  (failed=%d)",
            response.success_count, len(tokens), response.failure_count,
        )

        # Log token-level failures
        for i, resp in enumerate(response.responses):
            if not resp.success:
                logger.warning("[FCM] Token[%d] failed: %s", i, resp.exception)

        return response.success_count

    except Exception as exc:
        logger.error("[FCM] send_push error: %s", exc)
        return 0


def send_push_to_all_members(
    app,
    title: str,
    body: str,
    data: dict | None = None,
    dedup_key: str | None = None,
) -> int:
    try:
        # Dedup check
        key = dedup_key or f"{title}:{body}"
        if not _check_dedup(key):
            return 0

        with app.app_context():
            from app.entities.member_entity import MbMem
            raw_tokens = [
                m.mem_fcm
                for m in MbMem.query.filter(MbMem.mem_fcm.isnot(None)).all()
                if m.mem_fcm
            ]

        # Deduplicate — กรณี 2 accounts ลง token บน device เดียวกัน
        tokens = list(dict.fromkeys(raw_tokens))
        if len(tokens) < len(raw_tokens):
            logger.warning("[FCM] Deduped tokens: %d → %d (same device registered twice)",
                           len(raw_tokens), len(tokens))
        logger.info("[FCM] Found %d FCM token(s) to notify", len(tokens))
        return send_push_to_tokens(tokens, title, body, data)

    except Exception as exc:
        logger.error("[FCM] send_push_to_all_members error: %s", exc)
        return 0
