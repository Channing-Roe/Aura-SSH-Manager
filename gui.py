"""
gui.py - Main application window and all GUI components.

Built with PyQt6. Layout:
  ┌──────────────┬──────────────────────────────────────────────┐
  │ Left Panel   │  Tab strip: [Terminal] [Stats] …             │
  │ (Saved       │──────────────────────────────────────────────│
  │  Servers)    │  Terminal or Stats panel                     │
  └──────────────┴──────────────────────────────────────────────┘

Uses a dark terminal-style colour palette throughout.
"""

import sys
import time
import threading
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QLabel, QPushButton, QLineEdit, QTabWidget,
    QTextEdit, QListWidget, QListWidgetItem, QDialog, QFormLayout,
    QComboBox, QSpinBox, QFileDialog, QMessageBox, QFrame,
    QScrollArea, QGridLayout, QProgressBar, QTableWidget,
    QTableWidgetItem, QHeaderView, QGroupBox, QCheckBox,
    QInputDialog, QStatusBar,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread
from PyQt6.QtGui import (
    QFont, QColor, QPalette, QTextCursor, QIcon,
    QFontDatabase, QKeyEvent,
)

from encryption import (
    load_profiles, save_profiles, has_master_key,
    initialize_master_key, verify_master_password,
)
from ssh_client import SSHSession
from screen_viewer import ScreenViewerPanel


# ── Colour palette ─────────────────────────────────────────────────────────────
BG_DARK     = "#0d1117"
BG_MEDIUM   = "#161b22"
BG_LIGHT    = "#21262d"
BORDER      = "#30363d"
TEXT_PRIMARY   = "#e6edf3"
TEXT_SECONDARY = "#8b949e"
ACCENT_GREEN   = "#3fb950"
ACCENT_BLUE    = "#58a6ff"
ACCENT_YELLOW  = "#d29922"
ACCENT_RED     = "#f85149"
ACCENT_PURPLE  = "#bc8cff"
TERMINAL_BG    = "#010409"
TERMINAL_FG    = "#c9d1d9"


# ── Stylesheet ─────────────────────────────────────────────────────────────────
APP_STYLE = f"""
QMainWindow, QWidget {{
    background-color: {BG_DARK};
    color: {TEXT_PRIMARY};
    font-family: 'Segoe UI', 'SF Pro Text', Ubuntu, sans-serif;
    font-size: 13px;
}}
QSplitter::handle {{
    background-color: {BORDER};
    width: 1px;
}}
QPushButton {{
    background-color: {BG_LIGHT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 12px;
}}
QPushButton:hover  {{ background-color: #2d333b; border-color: {ACCENT_BLUE}; }}
QPushButton:pressed {{ background-color: {BG_MEDIUM}; }}
QPushButton#primary {{
    background-color: {ACCENT_GREEN};
    color: #000;
    border: none;
    font-weight: 600;
}}
QPushButton#primary:hover {{ background-color: #3dd64a; }}
QPushButton#danger {{
    background-color: {ACCENT_RED};
    color: #fff;
    border: none;
    font-weight: 600;
}}
QPushButton#danger:hover {{ background-color: #ff6b6b; }}
QLineEdit, QSpinBox, QComboBox {{
    background-color: {BG_MEDIUM};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
    selection-background-color: {ACCENT_BLUE};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {ACCENT_BLUE};
    outline: none;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_MEDIUM};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT_BLUE};
}}
QTabWidget::pane {{
    border: 1px solid {BORDER};
    background-color: {BG_MEDIUM};
    border-radius: 0 6px 6px 6px;
}}
QTabBar::tab {{
    background-color: {BG_DARK};
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER};
    border-bottom: none;
    padding: 8px 18px;
    margin-right: 2px;
    border-radius: 6px 6px 0 0;
    font-size: 12px;
}}
QTabBar::tab:selected {{
    background-color: {BG_MEDIUM};
    color: {TEXT_PRIMARY};
    border-bottom: 2px solid {ACCENT_BLUE};
}}
QTabBar::tab:hover {{ color: {TEXT_PRIMARY}; }}
QListWidget {{
    background-color: {BG_MEDIUM};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    outline: none;
}}
QListWidget::item {{
    padding: 8px 12px;
    border-radius: 4px;
    margin: 1px 4px;
}}
QListWidget::item:selected {{
    background-color: {ACCENT_BLUE};
    color: #000;
    font-weight: 600;
}}
QListWidget::item:hover {{ background-color: {BG_LIGHT}; }}
QScrollBar:vertical {{
    background: {BG_DARK};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{ background: {TEXT_SECONDARY}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QTableWidget {{
    background-color: {BG_MEDIUM};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    gridline-color: {BORDER};
    outline: none;
}}
QTableWidget::item {{ padding: 6px 8px; }}
QTableWidget::item:selected {{
    background-color: {ACCENT_BLUE};
    color: #000;
}}
QHeaderView::section {{
    background-color: {BG_LIGHT};
    color: {TEXT_SECONDARY};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 8px;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
QProgressBar {{
    background-color: {BG_LIGHT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    text-align: center;
    color: {TEXT_PRIMARY};
    font-size: 11px;
    height: 18px;
}}
QProgressBar::chunk {{
    background-color: {ACCENT_BLUE};
    border-radius: 3px;
}}
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 12px;
    padding: 10px;
    font-weight: 600;
    color: {TEXT_SECONDARY};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    left: 12px;
    top: -6px;
}}
QLabel#ethics {{
    background-color: #2d1b00;
    color: {ACCENT_YELLOW};
    border: 1px solid {ACCENT_YELLOW};
    border-radius: 6px;
    padding: 8px 14px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#status_connected {{
    color: {ACCENT_GREEN};
    font-weight: 600;
    font-size: 11px;
}}
QLabel#status_disconnected {{
    color: {TEXT_SECONDARY};
    font-size: 11px;
}}
QStatusBar {{
    background-color: {BG_MEDIUM};
    color: {TEXT_SECONDARY};
    border-top: 1px solid {BORDER};
    font-size: 11px;
}}
"""


# ── Signals helper ─────────────────────────────────────────────────────────────
class TerminalSignals(QObject):
    output_received = pyqtSignal(str)
    connected       = pyqtSignal()
    disconnected    = pyqtSignal(str)


class StatsSignals(QObject):
    stats_ready = pyqtSignal(dict)
    error       = pyqtSignal(str)


# ── Terminal widget ─────────────────────────────────────────────────────────────
class TerminalWidget(QWidget):
    """
    A single SSH terminal tab. Contains an output display and command input.
    """

    def __init__(self, session: SSHSession, parent=None):
        super().__init__(parent)
        self.session = session
        self.signals = TerminalSignals()
        self._setup_ui()
        self._start_shell()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Toolbar ──
        toolbar = QWidget()
        toolbar.setStyleSheet(f"background:{BG_LIGHT}; border-bottom:1px solid {BORDER};")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(8, 4, 8, 4)

        self.lbl_title = QLabel(f"  {self.session.session_id}")
        self.lbl_title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-weight:600; font-size:12px;")

        self.lbl_status = QLabel("● Connecting…")
        self.lbl_status.setStyleSheet(f"color:{ACCENT_YELLOW}; font-size:11px; font-weight:600;")

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setFixedHeight(26)
        self.btn_clear.clicked.connect(self._clear_output)

        tb_layout.addWidget(self.lbl_title)
        tb_layout.addStretch()
        tb_layout.addWidget(self.lbl_status)
        tb_layout.addSpacing(12)
        tb_layout.addWidget(self.btn_clear)

        # ── Output area ──
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet(
            f"background-color:{TERMINAL_BG}; color:{TERMINAL_FG};"
            f"border:none; padding:8px;"
            f"font-family:'Cascadia Code','JetBrains Mono','Fira Code','Consolas',monospace;"
            f"font-size:13px; line-height:1.4;"
        )
        self.output.document().setMaximumBlockCount(5000)

        # ── Input row ──
        input_row = QWidget()
        input_row.setStyleSheet(f"background:{TERMINAL_BG}; border-top:1px solid {BORDER};")
        ir_layout = QHBoxLayout(input_row)
        ir_layout.setContentsMargins(8, 4, 8, 4)

        self.lbl_prompt = QLabel("$")
        self.lbl_prompt.setStyleSheet(
            f"color:{ACCENT_GREEN}; font-family:monospace; font-size:14px; font-weight:700;"
        )

        self.cmd_input = CommandLineEdit()
        self.cmd_input.setStyleSheet(
            f"background:transparent; color:{TERMINAL_FG}; border:none;"
            f"font-family:'Cascadia Code','JetBrains Mono','Fira Code','Consolas',monospace;"
            f"font-size:13px;"
        )
        self.cmd_input.setPlaceholderText("type command and press Enter…")
        self.cmd_input.returnPressed.connect(self._send_command)

        ir_layout.addWidget(self.lbl_prompt)
        ir_layout.addWidget(self.cmd_input, 1)

        layout.addWidget(toolbar)
        layout.addWidget(self.output, 1)
        layout.addWidget(input_row)

        # Connect signals
        self.signals.output_received.connect(self._append_output)
        self.signals.connected.connect(self._on_connected)
        self.signals.disconnected.connect(self._on_disconnected)

    def _start_shell(self):
        """Open the interactive shell in a background thread."""
        def run():
            ok = self.session.open_shell(
                lambda txt: self.signals.output_received.emit(txt)
            )
            if ok:
                self.signals.connected.emit()
            else:
                self.signals.disconnected.emit("Failed to open shell.")
        threading.Thread(target=run, daemon=True).start()

    def _send_command(self):
        text = self.cmd_input.text()
        if text:
            self.session.send_command(text)
            self.cmd_input.clear()

    def _append_output(self, text: str):
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.output.setTextCursor(cursor)
        self.output.ensureCursorVisible()

    def _clear_output(self):
        self.output.clear()

    def _on_connected(self):
        self.lbl_status.setText("● Connected")
        self.lbl_status.setStyleSheet(f"color:{ACCENT_GREEN}; font-size:11px; font-weight:600;")
        self.cmd_input.setEnabled(True)

    def _on_disconnected(self, reason: str):
        self.lbl_status.setText("● Disconnected")
        self.lbl_status.setStyleSheet(f"color:{ACCENT_RED}; font-size:11px; font-weight:600;")
        self._append_output(f"\r\n\r\n[Disconnected: {reason}]\r\n")
        self.cmd_input.setEnabled(False)

    def disconnect(self):
        self.session.disconnect()


class CommandLineEdit(QLineEdit):
    """QLineEdit with up-arrow command history."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history: list[str] = []
        self._hist_idx = -1

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Up:
            if self._history:
                self._hist_idx = max(0, self._hist_idx - 1)
                self.setText(self._history[self._hist_idx])
        elif event.key() == Qt.Key.Key_Down:
            if self._history:
                self._hist_idx = min(len(self._history) - 1, self._hist_idx + 1)
                self.setText(self._history[self._hist_idx])
        else:
            if event.key() == Qt.Key.Key_Return and self.text():
                self._history.append(self.text())
                self._hist_idx = len(self._history)
            super().keyPressEvent(event)


# ── Stats worker ────────────────────────────────────────────────────────────────
class StatsWorker(QThread):
    stats_ready = pyqtSignal(dict)
    error       = pyqtSignal(str)

    def __init__(self, session: SSHSession):
        super().__init__()
        self.session = session
        self._running = True

    def run(self):
        while self._running and self.session.is_connected:
            try:
                stats = self.session.get_system_stats()
                self.stats_ready.emit(stats)
            except Exception as e:
                self.error.emit(str(e))
            for _ in range(50):        # sleep 5 s in 0.1 s chunks
                if not self._running:
                    break
                time.sleep(0.1)

    def stop(self):
        self._running = False


# ── Stats panel ─────────────────────────────────────────────────────────────────
class StatsPanel(QWidget):
    """Remote system monitoring panel."""

    def __init__(self, session: SSHSession, parent=None):
        super().__init__(parent)
        self.session = session
        self.worker = StatsWorker(session)
        self.worker.stats_ready.connect(self._update)
        self.worker.error.connect(self._show_error)
        self._setup_ui()
        self.worker.start()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        hdr = QLabel(f"System Monitor — {self.session.session_id}")
        hdr.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:15px; font-weight:700;"
        )
        layout.addWidget(hdr)

        # Host info row
        info_group = QGroupBox("Host Information")
        info_layout = QGridLayout(info_group)
        self.lbl_hostname = self._info_label("—")
        self.lbl_os       = self._info_label("—")
        self.lbl_whoami   = self._info_label("—")
        self.lbl_uptime   = self._info_label("—")
        info_layout.addWidget(QLabel("Hostname:"), 0, 0)
        info_layout.addWidget(self.lbl_hostname, 0, 1)
        info_layout.addWidget(QLabel("OS:"), 0, 2)
        info_layout.addWidget(self.lbl_os, 0, 3)
        info_layout.addWidget(QLabel("User:"), 1, 0)
        info_layout.addWidget(self.lbl_whoami, 1, 1)
        info_layout.addWidget(QLabel("Uptime:"), 1, 2)
        info_layout.addWidget(self.lbl_uptime, 1, 3)
        layout.addWidget(info_group)

        # Metrics row
        metrics_row = QHBoxLayout()

        # CPU
        cpu_group = QGroupBox("CPU Usage")
        cpu_layout = QVBoxLayout(cpu_group)
        self.cpu_bar = QProgressBar()
        self.cpu_bar.setRange(0, 100)
        self.lbl_cpu_pct = QLabel("—")
        self.lbl_cpu_pct.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cpu_pct.setStyleSheet(f"font-size:28px; font-weight:700; color:{ACCENT_BLUE};")
        cpu_layout.addWidget(self.lbl_cpu_pct)
        cpu_layout.addWidget(self.cpu_bar)
        metrics_row.addWidget(cpu_group)

        # RAM
        ram_group = QGroupBox("Memory Usage")
        ram_layout = QVBoxLayout(ram_group)
        self.ram_bar = QProgressBar()
        self.ram_bar.setRange(0, 100)
        self.lbl_ram_pct = QLabel("—")
        self.lbl_ram_pct.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_ram_pct.setStyleSheet(f"font-size:28px; font-weight:700; color:{ACCENT_PURPLE};")
        self.lbl_ram_detail = QLabel("—")
        self.lbl_ram_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_ram_detail.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        ram_layout.addWidget(self.lbl_ram_pct)
        ram_layout.addWidget(self.ram_bar)
        ram_layout.addWidget(self.lbl_ram_detail)
        metrics_row.addWidget(ram_group)

        # Disk
        disk_group = QGroupBox("Disk Usage  (/)")
        disk_layout = QVBoxLayout(disk_group)
        self.disk_bar = QProgressBar()
        self.disk_bar.setRange(0, 100)
        self.lbl_disk_pct = QLabel("—")
        self.lbl_disk_pct.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_disk_pct.setStyleSheet(f"font-size:28px; font-weight:700; color:{ACCENT_GREEN};")
        self.lbl_disk_detail = QLabel("—")
        self.lbl_disk_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_disk_detail.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        disk_layout.addWidget(self.lbl_disk_pct)
        disk_layout.addWidget(self.disk_bar)
        disk_layout.addWidget(self.lbl_disk_detail)
        metrics_row.addWidget(disk_group)

        layout.addLayout(metrics_row)

        # Process table
        proc_group = QGroupBox("Top Processes (by CPU)")
        proc_layout = QVBoxLayout(proc_group)
        self.proc_table = QTableWidget(0, 4)
        self.proc_table.setHorizontalHeaderLabels(["User", "PID", "CPU %", "MEM %"])
        self.proc_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.proc_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.proc_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        proc_layout.addWidget(self.proc_table)
        layout.addWidget(proc_group, 1)

        self.lbl_last_update = QLabel("Refreshing…")
        self.lbl_last_update.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
        layout.addWidget(self.lbl_last_update)

    def _info_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color:{ACCENT_BLUE}; font-weight:600;")
        return lbl

    def _update(self, stats: dict):
        # Host info
        self.lbl_hostname.setText(stats.get("hostname", "—"))
        self.lbl_os.setText(stats.get("os", "—"))
        self.lbl_whoami.setText(stats.get("whoami", "—"))
        self.lbl_uptime.setText(stats.get("uptime", "—"))

        # CPU
        cpu = stats.get("cpu_pct", 0.0)
        self.cpu_bar.setValue(int(cpu))
        self.lbl_cpu_pct.setText(f"{cpu:.1f}%")
        self._color_bar(self.cpu_bar, cpu)

        # RAM
        ram = stats.get("ram", {})
        if "pct" in ram:
            pct = ram["pct"]
            self.ram_bar.setValue(int(pct))
            self.lbl_ram_pct.setText(f"{pct:.1f}%")
            self.lbl_ram_detail.setText(
                f"{ram.get('used','?')} / {ram.get('total','?')} MB"
            )
            self._color_bar(self.ram_bar, pct)
        else:
            self.lbl_ram_pct.setText("N/A")

        # Disk
        disk = stats.get("disk", {})
        if "pct" in disk:
            raw = disk["pct"].rstrip("%")
            try:
                pct = float(raw)
                self.disk_bar.setValue(int(pct))
                self.lbl_disk_pct.setText(f"{pct:.0f}%")
                self._color_bar(self.disk_bar, pct)
            except ValueError:
                self.lbl_disk_pct.setText("N/A")
            self.lbl_disk_detail.setText(
                f"Used {disk.get('used','?')} / {disk.get('total','?')}  "
                f"Free {disk.get('free','?')}"
            )

        # Processes
        procs = stats.get("processes", [])
        self.proc_table.setRowCount(len(procs))
        for row, p in enumerate(procs):
            self.proc_table.setItem(row, 0, QTableWidgetItem(p.get("user", "")))
            self.proc_table.setItem(row, 1, QTableWidgetItem(p.get("pid", "")))
            cpu_item = QTableWidgetItem(p.get("cpu", ""))
            mem_item = QTableWidgetItem(p.get("mem", ""))
            try:
                if float(p.get("cpu", 0)) > 50:
                    cpu_item.setForeground(QColor(ACCENT_RED))
            except ValueError:
                pass
            self.proc_table.setItem(row, 2, cpu_item)
            self.proc_table.setItem(row, 3, mem_item)

        from datetime import datetime
        self.lbl_last_update.setText(
            f"Last updated: {datetime.now():%H:%M:%S}  (auto-refresh every 5 s)"
        )

    def _color_bar(self, bar: QProgressBar, pct: float):
        if pct >= 85:
            color = ACCENT_RED
        elif pct >= 60:
            color = ACCENT_YELLOW
        else:
            color = ACCENT_BLUE
        bar.setStyleSheet(
            f"QProgressBar::chunk {{ background-color: {color}; border-radius: 3px; }}"
        )

    def _show_error(self, msg: str):
        self.lbl_last_update.setText(f"Error: {msg}")

    def stop(self):
        self.worker.stop()
        self.worker.wait(1000)


# ── Connection dialog ───────────────────────────────────────────────────────────
class ConnectionDialog(QDialog):
    """Dialog for creating or editing an SSH connection profile."""

    def __init__(self, parent=None, profile: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("SSH Connection Profile")
        self.setMinimumWidth(440)
        self.setStyleSheet(f"background:{BG_MEDIUM}; color:{TEXT_PRIMARY};")
        self.profile = profile or {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Title
        title = QLabel("New SSH Connection" if not self.profile else "Edit Connection")
        title.setStyleSheet(f"font-size:16px; font-weight:700; color:{TEXT_PRIMARY};")
        layout.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        def row_style(w):
            return w

        # Name
        self.name_input = QLineEdit(self.profile.get("name", ""))
        self.name_input.setPlaceholderText("My Server")
        form.addRow("Profile Name:", row_style(self.name_input))

        # Host
        self.host_input = QLineEdit(self.profile.get("host", ""))
        self.host_input.setPlaceholderText("192.168.1.100 or hostname")
        form.addRow("Host / IP:", row_style(self.host_input))

        # Port
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(self.profile.get("port", 22))
        form.addRow("Port:", row_style(self.port_input))

        # Username
        self.user_input = QLineEdit(self.profile.get("username", ""))
        self.user_input.setPlaceholderText("ubuntu / root / pi …")
        form.addRow("Username:", row_style(self.user_input))

        # Auth method
        self.auth_combo = QComboBox()
        self.auth_combo.addItems(["Password", "Private Key File"])
        self.auth_combo.currentIndexChanged.connect(self._toggle_auth)
        form.addRow("Auth Method:", row_style(self.auth_combo))

        # Password
        self.pwd_input = QLineEdit()
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_input.setPlaceholderText("(stored encrypted)")
        form.addRow("Password:", row_style(self.pwd_input))

        # Key file
        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        self.key_input = QLineEdit(self.profile.get("key_path", ""))
        self.key_input.setPlaceholderText("~/.ssh/id_rsa")
        btn_browse = QPushButton("Browse…")
        btn_browse.setFixedWidth(80)
        btn_browse.clicked.connect(self._browse_key)
        key_layout.addWidget(self.key_input)
        key_layout.addWidget(btn_browse)
        form.addRow("Key File:", row_style(key_row))

        layout.addLayout(form)

        # Buttons
        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Save Profile")
        btn_save.setObjectName("primary")
        btn_save.clicked.connect(self._accept)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

        # Set initial state
        if self.profile.get("auth_method") == "key":
            self.auth_combo.setCurrentIndex(1)
        self._toggle_auth(self.auth_combo.currentIndex())

    def _toggle_auth(self, idx: int):
        self.pwd_input.setEnabled(idx == 0)
        # key widgets are always visible but enabled state toggles
        self.key_input.setEnabled(idx == 1)

    def _browse_key(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Private Key",
            str(Path.home() / ".ssh"),
            "All Files (*)"
        )
        if path:
            self.key_input.setText(path)

    def _accept(self):
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Validation", "Profile name is required.")
            return
        if not self.host_input.text().strip():
            QMessageBox.warning(self, "Validation", "Host is required.")
            return
        if not self.user_input.text().strip():
            QMessageBox.warning(self, "Validation", "Username is required.")
            return
        self.accept()

    def get_profile(self) -> dict:
        auth_method = "password" if self.auth_combo.currentIndex() == 0 else "key"
        return {
            "name":        self.name_input.text().strip(),
            "host":        self.host_input.text().strip(),
            "port":        self.port_input.value(),
            "username":    self.user_input.text().strip(),
            "auth_method": auth_method,
            "password":    self.pwd_input.text() if auth_method == "password" else "",
            "key_path":    self.key_input.text().strip() if auth_method == "key" else "",
        }


# ── Master password dialog ──────────────────────────────────────────────────────
class MasterPasswordDialog(QDialog):
    """Prompt for master password on startup."""

    def __init__(self, is_new: bool = False, parent=None):
        super().__init__(parent)
        self.is_new = is_new
        self.setWindowTitle("Aura SSH Manager — Vault Password")
        self.setMinimumWidth(380)
        self.setStyleSheet(f"background:{BG_MEDIUM}; color:{TEXT_PRIMARY};")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        icon_lbl = QLabel("🔐")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("font-size:36px;")
        layout.addWidget(icon_lbl)

        if self.is_new:
            msg = QLabel(
                "First run — choose a master password to encrypt your saved profiles.\n"
                "This password is NOT recoverable. Keep it safe."
            )
        else:
            msg = QLabel("Enter your master password to unlock the profile vault.")
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        layout.addWidget(msg)

        self.pwd_input = QLineEdit()
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_input.setPlaceholderText("Master password…")
        self.pwd_input.returnPressed.connect(self._accept)
        layout.addWidget(self.pwd_input)

        if self.is_new:
            self.confirm_input = QLineEdit()
            self.confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.confirm_input.setPlaceholderText("Confirm password…")
            self.confirm_input.returnPressed.connect(self._accept)
            layout.addWidget(self.confirm_input)

        btn = QPushButton("Unlock Vault" if not self.is_new else "Create Vault")
        btn.setObjectName("primary")
        btn.clicked.connect(self._accept)
        layout.addWidget(btn)

    def _accept(self):
        pwd = self.pwd_input.text()
        if not pwd:
            QMessageBox.warning(self, "Error", "Password cannot be empty.")
            return
        if self.is_new:
            confirm = self.confirm_input.text()
            if pwd != confirm:
                QMessageBox.warning(self, "Error", "Passwords do not match.")
                return
        self.accept()

    def get_password(self) -> str:
        return self.pwd_input.text()


# ── Connect worker ──────────────────────────────────────────────────────────────
class ConnectWorker(QThread):
    connected    = pyqtSignal(object)   # SSHSession
    failed       = pyqtSignal(str)

    def __init__(self, profile: dict):
        super().__init__()
        self.profile = profile

    def run(self):
        p = self.profile
        session = SSHSession(
            host=p["host"],
            port=p.get("port", 22),
            username=p["username"],
            password=p.get("password") or None,
            key_path=p.get("key_path") or None,
            session_id=p.get("name", f"{p['username']}@{p['host']}"),
        )
        ok, msg = session.connect()
        if ok:
            self.connected.emit(session)
        else:
            self.failed.emit(msg)


# ── Left panel (server list) ────────────────────────────────────────────────────
class ServerListPanel(QWidget):
    connect_requested = pyqtSignal(dict)

    def __init__(self, master_password: str, parent=None):
        super().__init__(parent)
        self.master_password = master_password
        self.profiles: dict = {}
        self._setup_ui()
        self._load_profiles()

    def _setup_ui(self):
        self.setFixedWidth(220)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(8)

        title = QLabel("  SERVERS")
        title.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:10px; font-weight:700; letter-spacing:1px;"
        )
        layout.addWidget(title)

        self.server_list = QListWidget()
        self.server_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.server_list.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.server_list, 1)

        btn_add = QPushButton("＋  Add Server")
        btn_add.setObjectName("primary")
        btn_add.clicked.connect(self._add_profile)
        layout.addWidget(btn_add)

        btn_connect = QPushButton("⚡  Connect")
        btn_connect.clicked.connect(self._connect_selected)
        layout.addWidget(btn_connect)

        btn_edit = QPushButton("✏  Edit")
        btn_edit.clicked.connect(self._edit_selected)
        layout.addWidget(btn_edit)

        btn_delete = QPushButton("🗑  Delete")
        btn_delete.setObjectName("danger")
        btn_delete.clicked.connect(self._delete_selected)
        layout.addWidget(btn_delete)

    def _load_profiles(self):
        self.profiles = load_profiles(self.master_password) or {}
        self._refresh_list()

    def _refresh_list(self):
        self.server_list.clear()
        for name, p in self.profiles.items():
            item = QListWidgetItem(f"  {name}")
            item.setToolTip(f"{p.get('username')}@{p.get('host')}:{p.get('port',22)}")
            self.server_list.addItem(item)

    def _save_profiles(self):
        save_profiles(self.profiles, self.master_password)

    def _add_profile(self):
        dlg = ConnectionDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            p = dlg.get_profile()
            self.profiles[p["name"]] = p
            self._save_profiles()
            self._refresh_list()

    def _edit_selected(self):
        item = self.server_list.currentItem()
        if not item:
            return
        name = item.text().strip()
        profile = self.profiles.get(name)
        if not profile:
            return
        dlg = ConnectionDialog(self, profile)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_p = dlg.get_profile()
            if new_p["name"] != name:
                del self.profiles[name]
            self.profiles[new_p["name"]] = new_p
            self._save_profiles()
            self._refresh_list()

    def _delete_selected(self):
        item = self.server_list.currentItem()
        if not item:
            return
        name = item.text().strip()
        resp = QMessageBox.question(
            self, "Delete Profile",
            f"Delete profile '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if resp == QMessageBox.StandardButton.Yes:
            self.profiles.pop(name, None)
            self._save_profiles()
            self._refresh_list()

    def _connect_selected(self):
        item = self.server_list.currentItem()
        if not item:
            QMessageBox.information(self, "Connect", "Select a server first.")
            return
        name = item.text().strip()
        profile = self.profiles.get(name)
        if profile:
            self.connect_requested.emit(profile)

    def _on_double_click(self, item: QListWidgetItem):
        name = item.text().strip()
        profile = self.profiles.get(name)
        if profile:
            self.connect_requested.emit(profile)


# ── Main window ─────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self, master_password: str):
        super().__init__()
        self.master_password = master_password
        self._connect_workers: list[ConnectWorker] = []
        self._active_stats: list[StatsPanel] = []
        self.setWindowTitle("Aura SSH Manager")
        self.setMinimumSize(1100, 700)
        self._setup_ui()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Ethics banner ──
        ethics = QLabel(
            "⚠  This tool is for authorized systems only.  "
            "Unauthorized access is illegal and unethical."
        )
        ethics.setObjectName("ethics")
        ethics.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ethics.setFixedHeight(32)
        root.addWidget(ethics)

        # ── Main splitter ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        self.server_panel = ServerListPanel(self.master_password)
        self.server_panel.connect_requested.connect(self._start_connect)

        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self._close_tab)
        self.tab_widget.setStyleSheet(
            f"QTabWidget::pane {{ background:{BG_MEDIUM}; }}"
        )

        # Placeholder tab
        placeholder = QWidget()
        ph_layout = QVBoxLayout(placeholder)
        ph_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel("Select a server and click Connect\nor double-click a saved profile")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:14px;")
        ph_layout.addWidget(lbl)
        self.tab_widget.addTab(placeholder, "Home")
        self.tab_widget.setTabsClosable(False)

        splitter.addWidget(self.server_panel)
        splitter.addWidget(self.tab_widget)
        splitter.setSizes([220, 880])

        root.addWidget(splitter, 1)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Aura SSH Manager v1.0  |  Vault encrypted with Fernet/PBKDF2")

    def _start_connect(self, profile: dict):
        self.status.showMessage(
            f"Connecting to {profile.get('username')}@{profile.get('host')}…"
        )
        worker = ConnectWorker(profile)
        worker.connected.connect(self._on_connected)
        worker.failed.connect(self._on_connect_failed)
        self._connect_workers.append(worker)
        worker.start()

    def _on_connected(self, session: SSHSession):
        self.status.showMessage(f"Connected to {session.session_id}")

        # Enable tab closing once a real tab exists
        if self.tab_widget.count() == 1:
            self.tab_widget.setTabsClosable(True)

        # Terminal tab
        terminal = TerminalWidget(session)
        idx = self.tab_widget.addTab(terminal, f"⚡ {session.session_id}")
        self.tab_widget.setCurrentIndex(idx)

        # Stats tab
        stats = StatsPanel(session)
        self._active_stats.append(stats)
        self.tab_widget.addTab(stats, f"📊 {session.session_id}")

        # Screen viewer tab
        screen = ScreenViewerPanel(session)
        self.tab_widget.addTab(screen, f"🖥  {session.session_id}")

    def _on_connect_failed(self, msg: str):
        self.status.showMessage(f"Connection failed: {msg}")
        QMessageBox.critical(self, "Connection Failed", msg)

    def _close_tab(self, idx: int):
        widget = self.tab_widget.widget(idx)
        if isinstance(widget, TerminalWidget):
            widget.disconnect()
        if isinstance(widget, StatsPanel):
            widget.stop()
            self._active_stats.remove(widget)
        if isinstance(widget, ScreenViewerPanel):
            widget.stop()
        self.tab_widget.removeTab(idx)
        if self.tab_widget.count() == 0:
            self.tab_widget.setTabsClosable(False)

    def closeEvent(self, event):
        # Clean up all sessions
        for i in range(self.tab_widget.count()):
            w = self.tab_widget.widget(i)
            if isinstance(w, TerminalWidget):
                w.disconnect()
            if isinstance(w, StatsPanel):
                w.stop()
            if isinstance(w, ScreenViewerPanel):
                w.stop()
        event.accept()
