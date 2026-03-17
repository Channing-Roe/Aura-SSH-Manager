#!/bin/bash
# ── Aura SSH Manager launcher (macOS / Linux) ─────────────────────
cd "$(dirname "$0")/aura_ssh_manager"
if ! python3 -c "import PyQt6" 2>/dev/null; then
    echo "Installing dependencies..."
    pip3 install -r requirements.txt
fi
python3 main.py
