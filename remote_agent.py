#!/usr/bin/env python3
"""
remote_agent.py  ──  Aura SSH Manager Screen Agent
═══════════════════════════════════════════════
Copy this file to your REMOTE machine and run it there.
It listens ONLY on 127.0.0.1 (localhost) — never on a public interface.
All traffic is tunnelled through your existing SSH connection.

Usage (on the remote machine):
    python3 remote_agent.py [--port 19876] [--quality 60] [--fps-cap 10]

Dependencies (remote machine only):
    pip install mss pillow

SECURITY NOTICE:
  • This agent listens on localhost only — not accessible from the network.
  • It accepts a one-time approval token printed at startup.
  • Stop the agent at any time with Ctrl+C.
  • Never run this on a machine you do not own or have authorisation to access.
"""

import argparse
import hashlib
import io
import logging
import os
import secrets
import socket
import struct
import sys
import threading
import time
from datetime import datetime

# ── Screenshot backend ────────────────────────────────────────────────────────
try:
    import mss
    import mss.tools
    _BACKEND = "mss"
except ImportError:
    _BACKEND = None

try:
    from PIL import ImageGrab, Image
    if _BACKEND is None:
        _BACKEND = "pil"
except ImportError:
    pass

if _BACKEND is None:
    print(
        "[agent] ERROR: No screenshot library found.\n"
        "Install with:  pip install mss pillow",
        file=sys.stderr,
    )
    sys.exit(1)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("screen_agent")

# ── Protocol constants ────────────────────────────────────────────────────────
CMD_SNAP  = b"SNAP\n"      # request one screenshot
CMD_PING  = b"PING\n"      # keepalive check
CMD_AUTH  = b"AUTH "       # AUTH <token>\n  — sent by client first
RESP_OK   = b"OK\n"
RESP_DENY = b"DENY\n"
RESP_PONG = b"PONG\n"


def capture_screenshot(quality: int = 70) -> bytes:
    """Capture full screen and return JPEG bytes."""
    if _BACKEND == "mss":
        with mss.mss() as sct:
            monitor = sct.monitors[0]   # full virtual screen (all monitors)
            shot = sct.grab(monitor)
            from PIL import Image as PILImage
            img = PILImage.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            return buf.getvalue()
    elif _BACKEND == "pil":
        img = ImageGrab.grab(all_screens=True)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        return buf.getvalue()
    else:
        raise RuntimeError("No screenshot backend available.")


def send_frame(conn: socket.socket, data: bytes):
    """Send 4-byte big-endian length prefix followed by frame bytes."""
    conn.sendall(struct.pack(">I", len(data)) + data)


def handle_client(
    conn: socket.socket,
    addr: tuple,
    token: str,
    quality: int,
    fps_cap: int,
):
    """Handle a single client connection with token auth."""
    logger.info("Client connected from %s", addr)
    authenticated = False
    min_interval = 1.0 / fps_cap if fps_cap > 0 else 0.1
    last_frame_time = 0.0

    try:
        conn.settimeout(30.0)

        # ── Auth handshake ────────────────────────────────────────────────────
        # Expect: AUTH <token>\n  within 10 seconds
        conn.settimeout(10.0)
        header = b""
        while b"\n" not in header:
            chunk = conn.recv(128)
            if not chunk:
                return
            header += chunk

        line = header.strip()
        if line.startswith(CMD_AUTH.strip()):
            received_token = line[5:].decode("utf-8", errors="replace").strip()
            # Constant-time comparison to prevent timing attacks
            if secrets.compare_digest(received_token, token):
                authenticated = True
                conn.sendall(RESP_OK)
                logger.info("Client %s authenticated successfully.", addr)
            else:
                conn.sendall(RESP_DENY)
                logger.warning("Client %s failed authentication.", addr)
                return
        else:
            conn.sendall(RESP_DENY)
            return

        # ── Command loop ──────────────────────────────────────────────────────
        conn.settimeout(60.0)
        while True:
            cmd = conn.recv(8)
            if not cmd:
                break

            if cmd.strip() == CMD_PING.strip():
                conn.sendall(RESP_PONG)

            elif cmd.strip() == CMD_SNAP.strip():
                # Rate limit
                now = time.monotonic()
                wait = min_interval - (now - last_frame_time)
                if wait > 0:
                    time.sleep(wait)
                last_frame_time = time.monotonic()

                frame = capture_screenshot(quality)
                send_frame(conn, frame)

            else:
                logger.warning("Unknown command from %s: %r", addr, cmd)
                break

    except (ConnectionResetError, BrokenPipeError, TimeoutError):
        pass
    except Exception as e:
        logger.error("Error handling client %s: %s", addr, e)
    finally:
        conn.close()
        logger.info("Client %s disconnected.", addr)


def run_server(host: str, port: int, token: str, quality: int, fps_cap: int):
    """Main server loop."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind((host, port))
    except OSError as e:
        logger.error("Cannot bind to %s:%d — %s", host, port, e)
        sys.exit(1)
    server.listen(3)

    print(
        f"\n{'═'*60}\n"
        f"  Aura SSH Manager Screen Agent\n"
        f"{'─'*60}\n"
        f"  Listening : {host}:{port}\n"
        f"  Backend   : {_BACKEND}\n"
        f"  Quality   : {quality}%  |  FPS cap: {fps_cap}\n"
        f"  Auth token: {token}\n"
        f"{'─'*60}\n"
        f"  ⚠  This token is required by the remote viewer.\n"
        f"     Copy it into the Screen Viewer panel in Aura SSH Manager.\n"
        f"{'═'*60}\n"
        f"  Press Ctrl+C to stop.\n",
        flush=True,
    )

    try:
        while True:
            conn, addr = server.accept()
            t = threading.Thread(
                target=handle_client,
                args=(conn, addr, token, quality, fps_cap),
                daemon=True,
            )
            t.start()
    except KeyboardInterrupt:
        print("\n[agent] Stopped.")
    finally:
        server.close()


def main():
    parser = argparse.ArgumentParser(description="Aura SSH Manager Screen Agent")
    parser.add_argument("--port",    type=int, default=19876,
                        help="Port to listen on (default: 19876)")
    parser.add_argument("--quality", type=int, default=65,
                        help="JPEG quality 10-95 (default: 65)")
    parser.add_argument("--fps-cap", type=int, default=8,
                        help="Max frames per second (default: 8)")
    parser.add_argument("--token",   type=str, default=None,
                        help="Override auth token (default: random)")
    args = parser.parse_args()

    token = args.token or secrets.token_urlsafe(16)

    run_server(
        host="127.0.0.1",    # ALWAYS localhost only
        port=args.port,
        token=token,
        quality=max(10, min(95, args.quality)),
        fps_cap=max(1, min(30, args.fps_cap)),
    )


if __name__ == "__main__":
    main()
