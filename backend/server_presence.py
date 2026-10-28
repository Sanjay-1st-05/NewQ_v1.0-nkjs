"""Stage 7b: automatic server discovery for the mobile app.

The PC's hotspot-assigned IP churns (a new subnet is leased every time
the hotspot restarts), so a hardcoded address in the app breaks after a
while. This module publishes the backend's current LAN address to a
Firestore document every minute:

    config/apiServer -> { host, port, hostname, updatedAt }

The mobile app reads that document (Firestore rules allow open read on
/config/* — the document contains a LAN address only, nothing secret)
and connects to the freshest entry, falling back to its bundled URL.

Writes use the Firebase Admin SDK, which bypasses Firestore rules, so
publishing works even though client writes stay locked.
"""

import asyncio
import logging
import socket
import time

logger = logging.getLogger("newq.presence")

PRESENCE_COLLECTION = "config"
PRESENCE_DOCUMENT = "apiServer"
# Publish immediately, then refresh at this interval. Cheap (one Firestore
# write per minute sits far below the free-tier quota).
HEARTBEAT_INTERVAL_SECONDS = 60.0

_task: asyncio.Task | None = None


def _is_publishable(ip: str) -> bool:
    """Whether a candidate address is one a hotspot peer could reach."""
    return (
        bool(ip)
        and not ip.startswith("127.")        # loopback
        and not ip.startswith("169.254.")    # link-local / DHCP failure
        and not ip.startswith("192.168.56.")  # VirtualBox host-only adapter
        and not ip.startswith("192.168.137.")  # Windows ICS hotspot adapter
    )


def pick_lan_ip() -> str:
    """Best-effort address of the interface a phone on the same LAN can reach.

    The UDP-probe trick connects a socket (no packets sent) toward a
    public address, which makes the OS pick the default-route interface —
    exactly the one a hotspot peer would use.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        ip = probe.getsockname()[0]
        if _is_publishable(ip):
            return ip
    except OSError:
        pass
    finally:
        probe.close()

    # Fallback: enumerate local addresses, preferring 10.x hotspots.
    candidates: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if _is_publishable(ip) and ip not in candidates:
                candidates.append(ip)
    except OSError:
        pass
    for ip in candidates:
        if ip.startswith("10."):
            return ip
    return candidates[0] if candidates else ""


def _publish_once(port: int) -> str:
    """Write one presence heartbeat. Returns the published host or ''."""
    import firebase_admin
    from firebase_admin import firestore

    host = pick_lan_ip()
    if not host:
        logger.warning("[PRESENCE] no publishable LAN address found")
        return ""

    db = firestore.client(firebase_admin.get_app())
    db.collection(PRESENCE_COLLECTION).document(PRESENCE_DOCUMENT).set(
        {
            "host": host,
            "port": int(port),
            "hostname": socket.gethostname(),
            "updatedAt": int(time.time() * 1000),
        }
    )
    return host


def presence_available() -> bool:
    """Whether we can publish (service account configured and usable)."""
    from backend import auth as stage7_auth

    if not stage7_auth.is_service_account_configured():
        return False
    stage7_auth._ensure_initialized()
    return stage7_auth._initialized


async def heartbeat_loop(port: int) -> None:
    """Publish presence at a fixed interval until the app shuts down."""
    while True:
        try:
            await asyncio.to_thread(_publish_once, port)
        except Exception as exc:  # Firestore hiccups must not kill the loop
            logger.warning("[PRESENCE] heartbeat failed: %s", exc)
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)


async def start_presence(port: int) -> asyncio.Task | None:
    """Publish once immediately, then schedule the heartbeat task."""
    global _task
    if _task and not _task.done():
        return _task
    if not presence_available():
        logger.info(
            "[PRESENCE] disabled — no service-account JSON, mobile app uses bundled URL"
        )
        return None
    try:
        host = await asyncio.to_thread(_publish_once, port)
    except Exception as exc:
        logger.warning("[PRESENCE] initial publish failed: %s", exc)
        host = ""
    else:
        if host:
            print(f"[PRESENCE] publishing {host}:{port} to Firestore every 60s")
    _task = asyncio.create_task(heartbeat_loop(port))
    return _task


def stop_presence() -> None:
    global _task
    if _task:
        _task.cancel()
        _task = None
