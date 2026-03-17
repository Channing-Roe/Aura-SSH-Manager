"""
main.py - Entry point for Aura SSH Manager.

Handles:
  1. Master-password vault setup / unlock
  2. Application launch

ETHICS NOTICE:
    This application is designed exclusively for managing servers you own
    or have explicit written authorisation to access. Connecting to systems
    without authorisation is illegal under the Computer Fraud and Abuse Act
    (US), the Computer Misuse Act (UK), and equivalent laws worldwide.
"""

import sys
from PyQt6.QtWidgets import QApplication, QMessageBox

from encryption import has_master_key, initialize_master_key, verify_master_password
from gui import MainWindow, MasterPasswordDialog, APP_STYLE


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Aura SSH Manager")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Aura")
    app.setStyleSheet(APP_STYLE)

    # ── Step 1: Master password ────────────────────────────────────────────────
    is_new_vault = not has_master_key()
    master_pwd = None

    for attempt in range(3):
        dlg = MasterPasswordDialog(is_new=is_new_vault)
        result = dlg.exec()

        if result != dlg.DialogCode.Accepted:
            sys.exit(0)

        pwd = dlg.get_password()

        if is_new_vault:
            initialize_master_key(pwd)
            master_pwd = pwd
            break
        else:
            if verify_master_password(pwd):
                master_pwd = pwd
                break
            else:
                remaining = 2 - attempt
                if remaining > 0:
                    QMessageBox.warning(
                        None,
                        "Wrong Password",
                        f"Incorrect master password. {remaining} attempt(s) remaining.",
                    )
                else:
                    QMessageBox.critical(
                        None,
                        "Access Denied",
                        "Too many failed attempts. Application will exit.",
                    )
                    sys.exit(1)

    if master_pwd is None:
        sys.exit(1)

    # ── Step 2: Launch main window ─────────────────────────────────────────────
    window = MainWindow(master_password=master_pwd)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
