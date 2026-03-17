"""
screen_viewer.py  ──  Live Screen Viewer Panel
═══════════════════════════════════════════════
Connects to a running remote_agent.py instance via an SSH tunnel.
All traffic travels inside the existing SSH connection — no extra ports
need to be opened in firewalls or security groups.

Architecture:
  [This app]  ←── SSH tunnel ───→  [remote_agent.py on remote machine]
    QLabel                            127.0.0.1:19876 (localhost only)

Tunnel is created with paramiko's direct-tcpip channel, which asks the
SSH server to forward traffic from a local socket to remote localhost:PORT.
No separate SSH process or port forwarding configuration is needed.
"""

import io
import socket
import struct
import threading
import time
from typing import Callable

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QObject
from PyQt6.QtGui import QPixmap, QImage, QFont, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QComboBox, QLineEdit, QGroupBox, QFrame,
    QSizePolicy, QScrollArea, QMessageBox, QSpinBox,
    QFormLayout, QCheckBox,
)

from ssh_client import SSHSession

# ── Protocol ──────────────────────────────────────────────────────────────────
CMD_SNAP  = b"SNAP\n"
CMD_PING  = b"PING\n"
RESP_OK   = b"OK\n"
RESP_DENY = b"DENY\n"
RESP_PONG = b"PONG\n"

# ── Colour constants (same palette as gui.py) ─────────────────────────────────
BG_DARK      = "#0d1117"
BG_MEDIUM    = "#161b22"
BG_LIGHT     = "#21262d"
BORDER       = "#30363d"
TEXT_PRIMARY    = "#e6edf3"
TEXT_SECONDARY  = "#8b949e"
ACCENT_GREEN    = "#3fb950"
ACCENT_BLUE     = "#58a6ff"
ACCENT_YELLOW   = "#d29922"
ACCENT_RED      = "#f85149"
ACCENT_PURPLE   = "#bc8cff"


# ── Low-level tunnel socket ───────────────────────────────────────────────────
class TunnelSocket:
    """
    Wraps a paramiko Channel to look like a standard socket.
    The channel is opened as direct-tcpip, which asks the SSH server to
    connect to remote_host:remote_port on the remote machine's localhost.
    """

    def __init__(self, session: SSHSession, remote_port: int):
        self._session = session
        self._remote_port = remote_port
        self._channel = None

    def connect(self) -> tuple[bool, str]:
        try:
            transport = self._session._client.get_transport()
            # direct-tcpip: ask server to connect to its own localhost:PORT
            self._channel = transport.open_channel(
                "direct-tcpip",
                dest_addr=("127.0.0.1", self._remote_port),
                src_addr=("127.0.0.1", 0),
                timeout=10,
            )
            return True, "Tunnel open."
        except Exception as e:
            return False, str(e)

    def send(self, data: bytes):
        if self._channel:
            self._channel.sendall(data)

    def recv(self, n: int) -> bytes:
        if self._channel:
            return self._channel.recv(n)
        return b""

    def recv_exactly(self, n: int) -> bytes:
        """Block until exactly n bytes are received."""
        buf = b""
        while len(buf) < n:
            chunk = self.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Tunnel closed unexpectedly.")
            buf += chunk
        return buf

    def close(self):
        if self._channel:
            try:
                self._channel.close()
            except Exception:
                pass
            self._channel = None

    @property
    def is_open(self) -> bool:
        return (
            self._channel is not None
            and not self._channel.closed
            and self._session.is_connected
        )


# ── Viewer worker thread ──────────────────────────────────────────────────────
class ViewerWorker(QThread):
    """
    Background thread: connects tunnel, authenticates, polls for frames.
    Emits frame_ready with raw JPEG bytes; parent converts to QPixmap.
    """
    frame_ready    = pyqtSignal(bytes)
    status_changed = pyqtSignal(str, str)   # (message, colour)
    error          = pyqtSignal(str)

    def __init__(
        self,
        session: SSHSession,
        token: str,
        remote_port: int = 19876,
        interval_ms: int = 500,
    ):
        super().__init__()
        self.session = session
        self.token = token
        self.remote_port = remote_port
        self.interval_ms = interval_ms
        self._running = False
        self._paused  = False
        self._lock = threading.Lock()

    def run(self):
        self._running = True
        self.status_changed.emit("Connecting tunnel…", ACCENT_YELLOW)

        tunnel = TunnelSocket(self.session, self.remote_port)
        ok, msg = tunnel.connect()
        if not ok:
            self.error.emit(f"Could not open SSH tunnel: {msg}")
            return

        # ── Auth handshake ────────────────────────────────────────────────────
        try:
            auth_cmd = f"AUTH {self.token}\n".encode()
            tunnel.send(auth_cmd)
            resp = tunnel.recv_exactly(3)       # "OK\n" or "DENY\n" (5 bytes)
            if resp == b"OK\n":
                self.status_changed.emit("Connected", ACCENT_GREEN)
            else:
                # Read rest of DENY response
                tunnel.close()
                self.error.emit(
                    "Agent rejected the auth token.\n"
                    "Make sure you copied the token exactly from the agent output."
                )
                return
        except Exception as e:
            tunnel.close()
            self.error.emit(f"Auth handshake failed: {e}")
            return

        # ── Frame loop ────────────────────────────────────────────────────────
        frames_received = 0
        last_ping = time.monotonic()

        while self._running and tunnel.is_open:
            if self._paused:
                time.sleep(0.1)
                continue

            try:
                # Request a frame
                tunnel.send(CMD_SNAP)

                # Read 4-byte length prefix
                raw_len = tunnel.recv_exactly(4)
                frame_len = struct.unpack(">I", raw_len)[0]

                if frame_len == 0 or frame_len > 20_000_000:   # sanity: max 20 MB
                    self.error.emit(f"Invalid frame length: {frame_len}")
                    break

                # Read frame data
                jpeg_data = tunnel.recv_exactly(frame_len)
                self.frame_ready.emit(jpeg_data)
                frames_received += 1

                # Keepalive ping every 15 seconds
                now = time.monotonic()
                if now - last_ping > 15:
                    tunnel.send(CMD_PING)
                    tunnel.recv_exactly(5)   # PONG\n
                    last_ping = now

                # Throttle
                sleep_s = self.interval_ms / 1000.0
                deadline = time.monotonic() + sleep_s
                while time.monotonic() < deadline and self._running:
                    time.sleep(0.05)

            except ConnectionError as e:
                self.error.emit(f"Connection lost: {e}")
                break
            except Exception as e:
                if self._running:
                    self.error.emit(f"Stream error: {e}")
                break

        tunnel.close()
        if self._running:
            self.status_changed.emit("Disconnected", ACCENT_RED)
        self._running = False

    def set_interval(self, ms: int):
        with self._lock:
            self.interval_ms = max(100, ms)

    def pause(self):
        self._paused = True
        self.status_changed.emit("Paused", ACCENT_YELLOW)

    def resume(self):
        self._paused = False
        self.status_changed.emit("Connected", ACCENT_GREEN)

    def stop(self):
        self._running = False
        self._paused  = False
        self.wait(3000)


# ── Deploy helper (uploads + starts remote_agent.py via SSH) ─────────────────
class DeployWorker(QThread):
    """Uploads remote_agent.py to the server and starts it in a background process."""
    done  = pyqtSignal(bool, str)   # (success, message)

    def __init__(self, session: SSHSession, remote_port: int, quality: int, fps_cap: int):
        super().__init__()
        self.session = session
        self.remote_port = remote_port
        self.quality = quality
        self.fps_cap = fps_cap

    def run(self):
        import os
        local_agent = os.path.join(os.path.dirname(__file__), "remote_agent.py")
        if not os.path.exists(local_agent):
            self.done.emit(False, "remote_agent.py not found next to this application.")
            return

        try:
            # ── Upload via SFTP ───────────────────────────────────────────────
            sftp = self.session._client.open_sftp()
            remote_path = f"/tmp/aura_agent_{self.session.username}.py"
            sftp.put(local_agent, remote_path)
            sftp.chmod(remote_path, 0o700)
            sftp.close()

            # ── Install deps (non-blocking, best-effort) ──────────────────────
            self.session.exec(
                "pip3 install mss pillow --quiet --break-system-packages 2>/dev/null || true",
                timeout=60,
            )

            # ── Launch agent in background ────────────────────────────────────
            launch_cmd = (
                f"nohup python3 {remote_path} "
                f"--port {self.remote_port} "
                f"--quality {self.quality} "
                f"--fps-cap {self.fps_cap} "
                f"> /tmp/ssh_agent_out.log 2>&1 &"
            )
            ok, out = self.session.exec(launch_cmd, timeout=15)

            if ok:
                # Give it a moment to start and print the token
                time.sleep(2)
                ok2, log = self.session.exec(
                    "cat /tmp/ssh_agent_out.log 2>/dev/null || echo '(no log)'",
                    timeout=5,
                )
                self.done.emit(True, log)
            else:
                self.done.emit(False, f"Launch failed: {out}")

        except Exception as e:
            self.done.emit(False, str(e))


# ── Main panel widget ─────────────────────────────────────────────────────────
class ScreenViewerPanel(QWidget):
    """
    The live screen viewer tab.

    Workflow:
      1. User enters the auth token printed by remote_agent.py.
      2. Click "Start Viewer".
      3. The panel opens an SSH tunnel and begins requesting frames.

    Optionally the user can click "Deploy & Start Agent" to upload
    remote_agent.py to the server and launch it automatically.
    """

    def __init__(self, session: SSHSession, parent=None):
        super().__init__(parent)
        self.session = session
        self._worker: ViewerWorker | None = None
        self._deploy_worker: DeployWorker | None = None
        self._total_frames = 0
        self._setup_ui()
        self._fps_timer = QTimer(self)
        self._fps_timer.setInterval(1000)
        self._fps_timer.timeout.connect(self._update_fps)
        self._frame_count_last_sec = 0

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top toolbar ───────────────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setStyleSheet(
            f"background:{BG_LIGHT}; border-bottom:1px solid {BORDER};"
        )
        toolbar.setFixedHeight(48)
        tbl = QHBoxLayout(toolbar)
        tbl.setContentsMargins(12, 0, 12, 0)
        tbl.setSpacing(10)

        # Status dot
        self.lbl_status = QLabel("● Idle")
        self.lbl_status.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-weight:700; font-size:12px;"
        )
        tbl.addWidget(self.lbl_status)

        tbl.addSpacing(8)

        # Token input
        lbl_tok = QLabel("Auth token:")
        lbl_tok.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("paste token from agent output…")
        self.token_input.setFixedWidth(260)
        self.token_input.setStyleSheet(
            f"background:{BG_MEDIUM}; color:{TEXT_PRIMARY}; "
            f"border:1px solid {BORDER}; border-radius:5px; padding:4px 8px; font-size:12px;"
        )
        tbl.addWidget(lbl_tok)
        tbl.addWidget(self.token_input)

        # Port
        lbl_port = QLabel("Port:")
        lbl_port.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(19876)
        self.port_spin.setFixedWidth(80)
        self.port_spin.setStyleSheet(
            f"background:{BG_MEDIUM}; color:{TEXT_PRIMARY}; "
            f"border:1px solid {BORDER}; border-radius:5px; padding:4px; font-size:12px;"
        )
        tbl.addWidget(lbl_port)
        tbl.addWidget(self.port_spin)

        tbl.addSpacing(8)

        # Interval selector
        lbl_rate = QLabel("Refresh:")
        lbl_rate.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        self.interval_combo = QComboBox()
        self.interval_combo.addItems([
            "0.5 s (2 fps)", "1 s (1 fps)", "2 s", "5 s", "10 s",
        ])
        self.interval_combo.setCurrentIndex(1)
        self.interval_combo.setFixedWidth(120)
        self.interval_combo.setStyleSheet(
            f"background:{BG_MEDIUM}; color:{TEXT_PRIMARY}; "
            f"border:1px solid {BORDER}; border-radius:5px; padding:4px; font-size:12px;"
        )
        self.interval_combo.currentIndexChanged.connect(self._change_interval)
        tbl.addWidget(lbl_rate)
        tbl.addWidget(self.interval_combo)

        tbl.addStretch()

        # FPS counter
        self.lbl_fps = QLabel("")
        self.lbl_fps.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
        tbl.addWidget(self.lbl_fps)

        # Scale checkbox
        self.chk_scale = QCheckBox("Fit to window")
        self.chk_scale.setChecked(True)
        self.chk_scale.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        tbl.addWidget(self.chk_scale)

        # Pause/Resume
        self.btn_pause = QPushButton("⏸  Pause")
        self.btn_pause.setFixedHeight(30)
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_pause.setStyleSheet(
            f"background:{BG_MEDIUM}; color:{TEXT_PRIMARY}; "
            f"border:1px solid {BORDER}; border-radius:5px; padding:0 12px;"
        )
        tbl.addWidget(self.btn_pause)

        # Start / Stop
        self.btn_start = QPushButton("▶  Start Viewer")
        self.btn_start.setObjectName("primary")
        self.btn_start.setFixedHeight(30)
        self.btn_start.clicked.connect(self._toggle_stream)
        self.btn_start.setStyleSheet(
            f"background:{ACCENT_GREEN}; color:#000; font-weight:700; "
            f"border:none; border-radius:5px; padding:0 14px;"
        )
        tbl.addWidget(self.btn_start)

        root.addWidget(toolbar)

        # ── Main area: canvas + sidebar ───────────────────────────────────────
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Scrollable canvas
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(
            f"background:{TERMINAL_BG if False else BG_DARK}; border:none;"
        )
        canvas_container = QWidget()
        canvas_container.setStyleSheet(f"background:{BG_DARK};")
        canvas_layout = QVBoxLayout(canvas_container)
        canvas_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.screen_label = QLabel()
        self.screen_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screen_label.setStyleSheet(
            f"background:{BG_DARK}; border:1px solid {BORDER}; border-radius:4px;"
        )
        self.screen_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._show_placeholder()
        canvas_layout.addWidget(self.screen_label)
        self.scroll.setWidget(canvas_container)

        # Sidebar
        sidebar = self._build_sidebar()
        sidebar.setFixedWidth(230)

        body.addWidget(self.scroll, 1)
        body.addWidget(sidebar)

        root.addLayout(body, 1)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setStyleSheet(
            f"background:{BG_MEDIUM}; border-left:1px solid {BORDER};"
        )
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(12)

        # ── Deploy section ────────────────────────────────────────────────────
        deploy_group = QGroupBox("Deploy Agent")
        deploy_group.setStyleSheet(
            f"QGroupBox {{ border:1px solid {BORDER}; border-radius:8px; "
            f"margin-top:10px; padding:8px; color:{TEXT_SECONDARY}; "
            f"font-size:10px; font-weight:700; }}"
            f"QGroupBox::title {{ subcontrol-origin:margin; left:10px; top:-6px; "
            f"padding:0 4px; }}"
        )
        dg_layout = QVBoxLayout(deploy_group)

        info = QLabel(
            "Uploads remote_agent.py to the server and starts it.\n\n"
            "Requires Python 3 and pip on the remote machine."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
        dg_layout.addWidget(info)

        dg_form = QFormLayout()
        dg_form.setSpacing(4)
        self.deploy_quality = QSpinBox()
        self.deploy_quality.setRange(10, 95)
        self.deploy_quality.setValue(65)
        self.deploy_quality.setSuffix("%")
        self.deploy_quality.setStyleSheet(
            f"background:{BG_LIGHT}; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; "
            f"border-radius:4px; padding:3px; font-size:11px;"
        )
        self.deploy_fps = QSpinBox()
        self.deploy_fps.setRange(1, 15)
        self.deploy_fps.setValue(8)
        self.deploy_fps.setSuffix(" fps")
        self.deploy_fps.setStyleSheet(
            f"background:{BG_LIGHT}; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; "
            f"border-radius:4px; padding:3px; font-size:11px;"
        )
        dg_form.addRow("Quality:", self.deploy_quality)
        dg_form.addRow("FPS cap:", self.deploy_fps)
        dg_layout.addLayout(dg_form)

        self.btn_deploy = QPushButton("🚀  Deploy & Start Agent")
        self.btn_deploy.setStyleSheet(
            f"background:{ACCENT_BLUE}; color:#000; font-weight:700; "
            f"border:none; border-radius:5px; padding:6px;"
        )
        self.btn_deploy.clicked.connect(self._deploy_agent)
        dg_layout.addWidget(self.btn_deploy)

        self.lbl_deploy_status = QLabel("")
        self.lbl_deploy_status.setWordWrap(True)
        self.lbl_deploy_status.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
        dg_layout.addWidget(self.lbl_deploy_status)

        layout.addWidget(deploy_group)

        # ── Connection info ───────────────────────────────────────────────────
        info_group = QGroupBox("Session Info")
        info_group.setStyleSheet(
            f"QGroupBox {{ border:1px solid {BORDER}; border-radius:8px; "
            f"margin-top:10px; padding:8px; color:{TEXT_SECONDARY}; "
            f"font-size:10px; font-weight:700; }}"
            f"QGroupBox::title {{ subcontrol-origin:margin; left:10px; top:-6px; "
            f"padding:0 4px; }}"
        )
        ig_layout = QVBoxLayout(info_group)

        self.lbl_session_id   = self._sidebar_label(self.session.session_id)
        self.lbl_frames_total = self._sidebar_label("0 frames")
        self.lbl_resolution   = self._sidebar_label("—")

        for title, widget in [
            ("Server:", self.lbl_session_id),
            ("Frames rx:", self.lbl_frames_total),
            ("Resolution:", self.lbl_resolution),
        ]:
            row = QHBoxLayout()
            lbl = QLabel(title)
            lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
            lbl.setFixedWidth(68)
            row.addWidget(lbl)
            row.addWidget(widget)
            ig_layout.addLayout(row)

        layout.addWidget(info_group)

        # ── Manual instructions ───────────────────────────────────────────────
        manual_group = QGroupBox("Manual Setup")
        manual_group.setStyleSheet(
            f"QGroupBox {{ border:1px solid {BORDER}; border-radius:8px; "
            f"margin-top:10px; padding:8px; color:{TEXT_SECONDARY}; "
            f"font-size:10px; font-weight:700; }}"
            f"QGroupBox::title {{ subcontrol-origin:margin; left:10px; top:-6px; "
            f"padding:0 4px; }}"
        )
        mg_layout = QVBoxLayout(manual_group)
        manual_text = QLabel(
            "On the remote machine:\n\n"
            "1. Copy remote_agent.py\n"
            "2. pip install mss pillow\n"
            "3. python3 remote_agent.py\n"
            "4. Copy the printed token\n"
            "   into the Auth token field\n"
            "5. Click ▶ Start Viewer"
        )
        manual_text.setWordWrap(True)
        manual_text.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:10px; "
            f"font-family:'Cascadia Code','Consolas',monospace;"
        )
        mg_layout.addWidget(manual_text)
        layout.addWidget(manual_group)

        layout.addStretch()

        # Ethics notice
        ethics = QLabel(
            "⚠  For your own authorized\n   machines only."
        )
        ethics.setStyleSheet(
            f"background:#2d1b00; color:{ACCENT_YELLOW}; "
            f"border:1px solid {ACCENT_YELLOW}; border-radius:5px; "
            f"padding:6px 8px; font-size:10px; font-weight:600;"
        )
        ethics.setWordWrap(True)
        layout.addWidget(ethics)

        return sidebar

    def _sidebar_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color:{ACCENT_BLUE}; font-size:10px; font-weight:600;")
        lbl.setWordWrap(True)
        return lbl

    def _show_placeholder(self):
        self.screen_label.setText(
            "No stream active\n\n"
            "Start the agent on the remote machine,\n"
            "enter the auth token, then click  ▶ Start Viewer"
        )
        self.screen_label.setStyleSheet(
            f"background:{BG_DARK}; color:{TEXT_SECONDARY}; "
            f"font-size:13px; border:1px solid {BORDER}; border-radius:4px;"
        )
        self.screen_label.setPixmap(QPixmap())

    # ── Stream control ────────────────────────────────────────────────────────

    def _interval_ms(self) -> int:
        mapping = {0: 500, 1: 1000, 2: 2000, 3: 5000, 4: 10000}
        return mapping.get(self.interval_combo.currentIndex(), 1000)

    def _toggle_stream(self):
        if self._worker and self._worker.isRunning():
            self._stop_stream()
        else:
            self._start_stream()

    def _start_stream(self):
        token = self.token_input.text().strip()
        if not token:
            QMessageBox.warning(
                self, "Token Required",
                "Paste the auth token printed by remote_agent.py\ninto the Auth token field."
            )
            return

        self._worker = ViewerWorker(
            session=self.session,
            token=token,
            remote_port=self.port_spin.value(),
            interval_ms=self._interval_ms(),
        )
        self._worker.frame_ready.connect(self._on_frame)
        self._worker.status_changed.connect(self._on_status)
        self._worker.error.connect(self._on_error)
        self._worker.start()

        self.btn_start.setText("■  Stop Viewer")
        self.btn_start.setStyleSheet(
            f"background:{ACCENT_RED}; color:#fff; font-weight:700; "
            f"border:none; border-radius:5px; padding:0 14px;"
        )
        self.btn_pause.setEnabled(True)
        self._fps_timer.start()
        self._total_frames = 0
        self._frame_count_last_sec = 0

    def _stop_stream(self):
        if self._worker:
            self._worker.stop()
            self._worker = None
        self._fps_timer.stop()
        self.btn_start.setText("▶  Start Viewer")
        self.btn_start.setStyleSheet(
            f"background:{ACCENT_GREEN}; color:#000; font-weight:700; "
            f"border:none; border-radius:5px; padding:0 14px;"
        )
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("⏸  Pause")
        self._on_status("Stopped", TEXT_SECONDARY)
        self._show_placeholder()

    def _toggle_pause(self):
        if not self._worker:
            return
        if self._worker._paused:
            self._worker.resume()
            self.btn_pause.setText("⏸  Pause")
        else:
            self._worker.pause()
            self.btn_pause.setText("▶  Resume")

    def _change_interval(self, _):
        if self._worker:
            self._worker.set_interval(self._interval_ms())

    # ── Frame rendering ───────────────────────────────────────────────────────

    def _on_frame(self, jpeg: bytes):
        pixmap = QPixmap()
        pixmap.loadFromData(jpeg, "JPEG")
        if pixmap.isNull():
            return

        self._total_frames += 1
        self._frame_count_last_sec += 1
        self.lbl_frames_total.setText(f"{self._total_frames:,} frames")
        self.lbl_resolution.setText(f"{pixmap.width()} × {pixmap.height()}")

        if self.chk_scale.isChecked():
            scaled = pixmap.scaled(
                self.scroll.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.screen_label.setPixmap(scaled)
        else:
            self.screen_label.setPixmap(pixmap)

        self.screen_label.setStyleSheet(
            f"background:{BG_DARK}; border:none;"
        )

    def _update_fps(self):
        self.lbl_fps.setText(f"{self._frame_count_last_sec} fps")
        self._frame_count_last_sec = 0

    # ── Status / error ────────────────────────────────────────────────────────

    def _on_status(self, msg: str, colour: str):
        self.lbl_status.setText(f"● {msg}")
        self.lbl_status.setStyleSheet(
            f"color:{colour}; font-weight:700; font-size:12px;"
        )

    def _on_error(self, msg: str):
        self._on_status("Error", ACCENT_RED)
        QMessageBox.critical(self, "Screen Viewer Error", msg)
        self._stop_stream()

    # ── Deploy ────────────────────────────────────────────────────────────────

    def _deploy_agent(self):
        self.btn_deploy.setEnabled(False)
        self.lbl_deploy_status.setText("Uploading agent…")

        self._deploy_worker = DeployWorker(
            session=self.session,
            remote_port=self.port_spin.value(),
            quality=self.deploy_quality.value(),
            fps_cap=self.deploy_fps.value(),
        )
        self._deploy_worker.done.connect(self._on_deploy_done)
        self._deploy_worker.start()

    def _on_deploy_done(self, success: bool, log: str):
        self.btn_deploy.setEnabled(True)
        if success:
            # Try to parse the token from the agent's stdout log
            token = ""
            for line in log.splitlines():
                if "Auth token:" in line:
                    token = line.split("Auth token:")[-1].strip()
                    break
            if token:
                self.token_input.setText(token)
                self.lbl_deploy_status.setText(
                    f"✓ Agent started!\nToken auto-filled."
                )
                self.lbl_deploy_status.setStyleSheet(
                    f"color:{ACCENT_GREEN}; font-size:10px;"
                )
            else:
                self.lbl_deploy_status.setText(
                    "Agent started. Copy token from agent output manually."
                )
                self.lbl_deploy_status.setStyleSheet(
                    f"color:{ACCENT_YELLOW}; font-size:10px;"
                )
        else:
            self.lbl_deploy_status.setText(f"Deploy failed:\n{log[:200]}")
            self.lbl_deploy_status.setStyleSheet(
                f"color:{ACCENT_RED}; font-size:10px;"
            )

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def stop(self):
        self._fps_timer.stop()
        if self._worker:
            self._worker.stop()
        if self._deploy_worker and self._deploy_worker.isRunning():
            self._deploy_worker.wait(2000)
