"""
encryption.py - Secure credential encryption/decryption using Fernet symmetric encryption.

This module handles all cryptographic operations for storing SSH profiles securely.
Passwords are NEVER written to disk in plain text. The encryption key is derived
from a master password using PBKDF2HMAC with a random salt.
"""

import os
import json
import base64
import hashlib
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


# Directory where encrypted profiles and key material are stored
CONFIG_DIR = Path.home() / ".aura_aura_ssh_manager"
PROFILES_FILE = CONFIG_DIR / "profiles.enc"
KEY_FILE = CONFIG_DIR / "keyfile.salt"


def ensure_config_dir():
    """Create the config directory with restricted permissions (owner-only)."""
    CONFIG_DIR.mkdir(mode=0o700, exist_ok=True)


def _derive_key(master_password: str, salt: bytes) -> bytes:
    """
    Derive a 32-byte Fernet key from a master password + salt using PBKDF2HMAC.
    Uses 480,000 iterations (OWASP 2023 recommendation for SHA-256).
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    key_bytes = kdf.derive(master_password.encode("utf-8"))
    return base64.urlsafe_b64encode(key_bytes)


def initialize_master_key(master_password: str) -> bool:
    """
    Generate a random salt and store it. Called once on first run.
    Returns True on success.
    """
    ensure_config_dir()
    salt = os.urandom(32)
    KEY_FILE.write_bytes(salt)
    KEY_FILE.chmod(0o600)  # Owner read/write only
    return True


def load_fernet(master_password: str) -> Fernet | None:
    """
    Load the salt from disk and derive the Fernet cipher.
    Returns None if the key file doesn't exist yet.
    """
    if not KEY_FILE.exists():
        return None
    salt = KEY_FILE.read_bytes()
    key = _derive_key(master_password, salt)
    return Fernet(key)


def has_master_key() -> bool:
    """Check whether a master key salt has been generated."""
    return KEY_FILE.exists()


def save_profiles(profiles: dict, master_password: str) -> bool:
    """
    Encrypt and save the profiles dictionary to disk.
    `profiles` is a plain dict; it is JSON-serialised then encrypted.
    Returns True on success, False on failure.
    """
    try:
        ensure_config_dir()
        f = load_fernet(master_password)
        if f is None:
            initialize_master_key(master_password)
            f = load_fernet(master_password)
        raw = json.dumps(profiles).encode("utf-8")
        encrypted = f.encrypt(raw)
        PROFILES_FILE.write_bytes(encrypted)
        PROFILES_FILE.chmod(0o600)
        return True
    except Exception as e:
        print(f"[encryption] save_profiles error: {e}")
        return False


def load_profiles(master_password: str) -> dict | None:
    """
    Decrypt and return the profiles dictionary.
    Returns None if the file doesn't exist or decryption fails (wrong password).
    """
    if not PROFILES_FILE.exists():
        return {}
    try:
        f = load_fernet(master_password)
        if f is None:
            return {}
        encrypted = PROFILES_FILE.read_bytes()
        raw = f.decrypt(encrypted)
        return json.loads(raw.decode("utf-8"))
    except Exception:
        # Invalid token means wrong master password
        return None


def verify_master_password(master_password: str) -> bool:
    """
    Attempt to decrypt the profiles file to verify the master password.
    Returns True if decryption succeeds (or no profiles exist yet).
    """
    result = load_profiles(master_password)
    return result is not None
