╔══════════════════════════════════════════════════════╗
║           Aura SSH Manager  v1.0.0                   ║
║     Secure SSH Client + Remote Screen Viewer         ║
╚══════════════════════════════════════════════════════╝

⚠  ETHICS NOTICE: For your own authorised machines only.
   Unauthorised access is illegal worldwide.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUICK START
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Requirements: Python 3.11+

1. Install dependencies:
      pip install -r aura_ssh_manager/requirements.txt

2. Launch:
      macOS / Linux:  ./run.sh
      Windows:        run.bat

3. On first launch, create a master password to encrypt
   your saved server profiles.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILE STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

aura_ssh_manager/
├── main.py           Entry point
├── gui.py            PyQt6 UI
├── ssh_client.py     Paramiko SSH engine + monitoring
├── encryption.py     Fernet encryption + PBKDF2
├── screen_viewer.py  Live screen viewer (local side)
├── remote_agent.py   ← Copy to your REMOTE machine
├── requirements.txt  Python dependencies
└── README.md         Full documentation

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCREEN VIEWER SETUP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

On the remote machine:
  pip install mss pillow
  python3 remote_agent.py

Paste the printed token into the 🖥 Screen Viewer tab.
Or use "Deploy & Start Agent" to do it automatically.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATA STORAGE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

~/.aura_ssh_manager/
  profiles.enc   — encrypted vault
  keyfile.salt   — PBKDF2 salt (chmod 600)
  logs/          — connection logs

