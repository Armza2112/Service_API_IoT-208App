import json
import logging
import os

logger = logging.getLogger(__name__)

_initialized = False


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

        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            tokens=tokens,
            android=messaging.AndroidConfig(priority="high"),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(sound="default")
                )
            ),
            webpush=messaging.WebpushConfig(
                notification=messaging.WebpushNotification(
                    title=title,
                    body=body,
                    icon="https://baan208-iot.biz/icons/logo-iot208.png",
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


def send_push_to_all_members(app, title: str, body: str, data: dict | None = None) -> int:
    try:
        with app.app_context():
            from app.entities.member_entity import MbMem
            tokens = [
                m.mem_fcm
                for m in MbMem.query.filter(MbMem.mem_fcm.isnot(None)).all()
                if m.mem_fcm
            ]

        logger.info("[FCM] Found %d FCM token(s) to notify", len(tokens))
        return send_push_to_tokens(tokens, title, body, data)

    except Exception as exc:
        logger.error("[FCM] send_push_to_all_members error: %s", exc)
        return 0
