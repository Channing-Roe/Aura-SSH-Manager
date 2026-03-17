"""
ssh_client.py - SSH connection management and remote system monitoring.

Uses paramiko for all SSH operations. Supports both password and private-key
authentication. Monitoring data is collected via safe, read-only shell commands.

ETHICAL USE NOTICE: This module is designed exclusively for connecting to
machines you own or have explicit written authorisation to access.
"""

import time
import threading
import logging
from datetime import datetime
from pathlib import Path
import paramiko
from paramiko import SSHClient, AutoAddPolicy, RSAKey, ECDSAKey, Ed25519Key

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_DIR = Path.home() / ".aura_ssh_manager" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
log_file = LOG_DIR / f"connections_{datetime.now():%Y%m%d}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file),
    ],
)
logger = logging.getLogger("aura_ssh_manager")


# ── Read-only monitoring commands (safe, no system changes) ───────────────────
MONITOR_COMMANDS = {
    "cpu":     "top -bn1 | grep 'Cpu(s)' | awk '{print $2}' | tr -d '%us,'",
    "cpu_alt": "cat /proc/stat | head -1",          # fallback
    "ram":     "free -m | awk '/^Mem:/{print $2,$3,$4}'",
    "disk":    "df -h / | awk 'NR==2{print $2,$3,$4,$5}'",
    "uptime":  "uptime -p 2>/dev/null || uptime",
    "os":      "uname -sr",
    "procs":   (
        "ps aux --sort=-%cpu 2>/dev/null | "
        "awk 'NR>1 && NR<=16 {printf \"%s|%s|%s|%s\\n\",$1,$2,$3,$4}'"
    ),
    "procs_mac": (
        "ps aux | sort -k3 -rn | "
        "awk 'NR>1 && NR<=16 {printf \"%s|%s|%s|%s\\n\",$1,$2,$3,$4}'"
    ),
    "hostname": "hostname",
    "whoami":   "whoami",
}


class SSHSession:
    """
    Represents a single SSH session to one remote host.
    Thread-safe: output callbacks are fired from a background reader thread.
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str | None = None,
        key_path: str | None = None,
        timeout: int = 15,
        session_id: str | None = None,
    ):
        self.host = host
        self.port = port
        self.username = username
        self._password = password          # Never logged
        self.key_path = key_path
        self.timeout = timeout
        self.session_id = session_id or f"{username}@{host}:{port}"

        self._client: SSHClient | None = None
        self._channel = None                # Interactive shell channel
        self._connected = False
        self._reader_thread: threading.Thread | None = None
        self._output_callback = None        # Called with each chunk of output
        self._lock = threading.Lock()

    # ── Connection ─────────────────────────────────────────────────────────────

    def connect(self) -> tuple[bool, str]:
        """
        Open the SSH connection. Returns (success, message).
        Logs the attempt (never logs the password).
        """
        logger.info("Connecting to %s@%s:%s", self.username, self.host, self.port)
        try:
            client = SSHClient()
            # Use AutoAddPolicy for first connection; for production you would
            # use RejectPolicy and manage known_hosts yourself.
            client.set_missing_host_key_policy(AutoAddPolicy())

            connect_kwargs = dict(
                hostname=self.host,
                port=self.port,
                username=self.username,
                timeout=self.timeout,
                banner_timeout=self.timeout,
                auth_timeout=self.timeout,
            )

            if self.key_path:
                pkey = self._load_private_key(self.key_path)
                if pkey is None:
                    return False, "Failed to load private key file."
                connect_kwargs["pkey"] = pkey
            elif self._password:
                connect_kwargs["password"] = self._password
            else:
                return False, "No authentication method provided."

            client.connect(**connect_kwargs)
            self._client = client
            self._connected = True
            logger.info("Connected successfully to %s", self.session_id)
            return True, "Connected."

        except paramiko.AuthenticationException:
            logger.warning("Authentication failed for %s", self.session_id)
            return False, "Authentication failed. Check username/password/key."
        except paramiko.SSHException as e:
            logger.error("SSH error for %s: %s", self.session_id, e)
            return False, f"SSH error: {e}"
        except OSError as e:
            logger.error("Network error for %s: %s", self.session_id, e)
            return False, f"Network error: {e}"
        except Exception as e:
            logger.error("Unexpected error for %s: %s", self.session_id, e)
            return False, f"Error: {e}"

    def _load_private_key(self, key_path: str):
        """Try loading the key as RSA, ECDSA, or Ed25519."""
        for key_class in (RSAKey, ECDSAKey, Ed25519Key):
            try:
                return key_class.from_private_key_file(key_path)
            except (paramiko.SSHException, Exception):
                continue
        logger.error("Could not parse private key: %s", key_path)
        return None

    def disconnect(self):
        """Close the channel and transport cleanly."""
        self._connected = False
        if self._channel:
            try:
                self._channel.close()
            except Exception:
                pass
            self._channel = None
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        logger.info("Disconnected from %s", self.session_id)

    @property
    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    # ── Interactive shell ──────────────────────────────────────────────────────

    def open_shell(self, output_callback) -> bool:
        """
        Open an interactive PTY shell. `output_callback(text)` is called
        with decoded output from the remote shell.
        """
        if not self.is_connected:
            return False
        try:
            self._output_callback = output_callback
            transport = self._client.get_transport()
            self._channel = transport.open_session()
            self._channel.get_pty(term="xterm-256color", width=220, height=50)
            self._channel.invoke_shell()
            # Start background reader
            self._reader_thread = threading.Thread(
                target=self._read_loop, daemon=True
            )
            self._reader_thread.start()
            return True
        except Exception as e:
            logger.error("open_shell failed for %s: %s", self.session_id, e)
            return False

    def _read_loop(self):
        """Background thread: continuously read from channel and fire callback."""
        while self._connected and self._channel and not self._channel.closed:
            try:
                if self._channel.recv_ready():
                    data = self._channel.recv(4096)
                    if data and self._output_callback:
                        self._output_callback(data.decode("utf-8", errors="replace"))
                if self._channel.recv_stderr_ready():
                    data = self._channel.recv_stderr(4096)
                    if data and self._output_callback:
                        self._output_callback(data.decode("utf-8", errors="replace"))
                time.sleep(0.02)
            except Exception:
                break

    def send_command(self, command: str):
        """Send a command string to the interactive shell."""
        if self._channel and not self._channel.closed:
            self._channel.send(command + "\n")

    # ── One-shot exec (for monitoring) ─────────────────────────────────────────

    def exec(self, command: str, timeout: int = 10) -> tuple[bool, str]:
        """
        Execute a single command (non-interactive). Returns (success, output).
        Used by the monitoring subsystem.
        """
        if not self.is_connected:
            return False, "Not connected"
        try:
            _, stdout, stderr = self._client.exec_command(command, timeout=timeout)
            out = stdout.read().decode("utf-8", errors="replace").strip()
            err = stderr.read().decode("utf-8", errors="replace").strip()
            return True, out if out else err
        except Exception as e:
            return False, str(e)

    # ── System monitoring ──────────────────────────────────────────────────────

    def get_system_stats(self) -> dict:
        """
        Collect CPU, RAM, disk, uptime, OS, hostname info via read-only commands.
        Returns a dict suitable for the GUI stats panel.
        """
        stats = {}

        # Hostname & OS
        ok, val = self.exec(MONITOR_COMMANDS["hostname"])
        stats["hostname"] = val if ok else "unknown"

        ok, val = self.exec(MONITOR_COMMANDS["os"])
        stats["os"] = val if ok else "unknown"

        ok, val = self.exec(MONITOR_COMMANDS["whoami"])
        stats["whoami"] = val if ok else self.username

        # Uptime
        ok, val = self.exec(MONITOR_COMMANDS["uptime"])
        stats["uptime"] = val if ok else "unknown"

        # RAM  →  total used free
        ok, val = self.exec(MONITOR_COMMANDS["ram"])
        if ok and val:
            parts = val.split()
            if len(parts) >= 3:
                try:
                    total, used, free = int(parts[0]), int(parts[1]), int(parts[2])
                    pct = round(used / total * 100, 1) if total else 0
                    stats["ram"] = {"total": total, "used": used, "free": free, "pct": pct}
                except ValueError:
                    stats["ram"] = {"error": val}
            else:
                stats["ram"] = {"error": val}
        else:
            stats["ram"] = {"error": "unavailable"}

        # CPU  (try /proc/stat for accuracy)
        stats["cpu_pct"] = self._get_cpu_pct()

        # Disk  →  total used avail pct
        ok, val = self.exec(MONITOR_COMMANDS["disk"])
        if ok and val:
            parts = val.split()
            if len(parts) >= 4:
                stats["disk"] = {
                    "total": parts[0], "used": parts[1],
                    "free": parts[2], "pct": parts[3],
                }
            else:
                stats["disk"] = {"error": val}
        else:
            stats["disk"] = {"error": "unavailable"}

        # Processes
        stats["processes"] = self._get_processes()

        return stats

    def _get_cpu_pct(self) -> float:
        """Read two snapshots of /proc/stat to compute real CPU usage."""
        cmd = "cat /proc/stat | head -1"
        ok1, v1 = self.exec(cmd)
        if not ok1:
            # macOS fallback
            ok, val = self.exec(MONITOR_COMMANDS["cpu"])
            try:
                return float(val.strip()) if ok else 0.0
            except ValueError:
                return 0.0

        time.sleep(0.3)
        ok2, v2 = self.exec(cmd)
        if not ok2:
            return 0.0

        def parse(line):
            parts = line.split()[1:]
            return [int(x) for x in parts]

        try:
            t1 = parse(v1)
            t2 = parse(v2)
            idle1, idle2 = t1[3], t2[3]
            total1, total2 = sum(t1), sum(t2)
            delta_total = total2 - total1
            delta_idle = idle2 - idle1
            if delta_total == 0:
                return 0.0
            return round((1 - delta_idle / delta_total) * 100, 1)
        except (IndexError, ValueError):
            return 0.0

    def _get_processes(self) -> list[dict]:
        """Return top processes sorted by CPU usage."""
        ok, val = self.exec(MONITOR_COMMANDS["procs"])
        if not ok or not val:
            ok, val = self.exec(MONITOR_COMMANDS["procs_mac"])
        if not val:
            return []
        procs = []
        for line in val.splitlines():
            parts = line.split("|")
            if len(parts) == 4:
                procs.append({
                    "user": parts[0],
                    "pid":  parts[1],
                    "cpu":  parts[2],
                    "mem":  parts[3],
                })
        return procs
