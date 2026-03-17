# Aura SSH Manager

A secure, ethical desktop application for managing SSH connections to **your own servers**.

> ⚠️ **ETHICS NOTICE**: This tool is for authorized systems only.
> Unauthorized access to computer systems is illegal under the CFAA (US),
> Computer Misuse Act (UK), and equivalent laws worldwide.

---

## Features

| Feature | Details |
|---|---|
| **Multi-profile management** | Save unlimited server profiles, encrypted at rest |
| **Password & key auth** | Supports password, RSA, ECDSA, and Ed25519 keys |
| **Interactive terminal** | Full PTY shell with command history (↑ arrow) |
| **Multiple sessions** | Each connection opens its own tab |
| **System monitoring** | Live CPU, RAM, disk, uptime, top-processes panel |
| **Encrypted vault** | Profiles encrypted with Fernet + PBKDF2HMAC (480k iterations) |
| **Connection logging** | All connections logged to `~/.aura_aura_ssh_manager/logs/` |

---

## Requirements

- Python 3.11+
- pip

---

## Installation

```bash
# 1. Clone / download the project
cd aura_ssh_manager

# 2. (Recommended) Create a virtual environment
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
python main.py
```

---

## First Run

On first launch you will be prompted to **create a master password**.
This password encrypts all saved profiles using Fernet symmetric encryption
with a key derived via PBKDF2HMAC-SHA256 (480,000 iterations).

⚠️ This password **cannot be recovered**. If you lose it, delete
`~/.aura_aura_ssh_manager/keyfile.salt` and `~/.aura_aura_ssh_manager/profiles.enc`
to start fresh (all saved profiles will be lost).

---

## Project Structure

```
aura_ssh_manager/
├── main.py          # Entry point: vault unlock → launch GUI
├── gui.py           # All PyQt6 widgets: window, terminal, stats, dialogs
├── ssh_client.py    # Paramiko SSH sessions + system monitoring commands
├── encryption.py    # Fernet encryption, PBKDF2 key derivation, profile I/O
└── requirements.txt
```

---

## Security Notes

- Passwords are **never written to disk in plain text**
- The encryption key is derived from your master password + a random 32-byte salt stored in `~/.aura_aura_ssh_manager/keyfile.salt` (mode 0600)
- Profile data is stored in `~/.aura_aura_ssh_manager/profiles.enc` (mode 0600)
- Connection logs are written to `~/.aura_aura_ssh_manager/logs/`
- SSH host keys are accepted automatically on first connect (AutoAddPolicy); for higher security, switch to `RejectPolicy` and manage `~/.ssh/known_hosts` manually

---

## System Monitoring Commands Used

All monitoring commands are **read-only** and cause no system changes:

| Metric | Command |
|---|---|
| CPU | `/proc/stat` diff (two snapshots) |
| RAM | `free -m` |
| Disk | `df -h /` |
| Processes | `ps aux --sort=-%cpu` |
| Uptime | `uptime -p` |
| OS / Host | `uname -sr`, `hostname` |
