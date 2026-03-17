@echo off
REM ── Aura SSH Manager launcher (Windows) ──────────────────────────
cd /d "%~dp0aura_ssh_manager"
python -c "import PyQt6" 2>nul || (
    echo Installing dependencies...
    pip install -r requirements.txt
)
python main.py
