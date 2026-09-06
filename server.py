#!/usr/bin/env python3
"""
server.py — Root launcher for THE 22KT GOLD Python Backend Server
"""

import sys
from pathlib import Path

# Add project root and backend folder to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "backend"))

from backend.server import app, init_db, DB_PATH
import os

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 3000))
    print(f"\n[OK] THE 22KT GOLD Python Server running at http://localhost:{port}")
    print(f"[API] Admin Dashboard: http://localhost:{port}/admin-login.html")
    print(f"[API] Gold Rate API:   http://localhost:{port}/api/gold-rates")
    print(f"[DB]  Database:        {DB_PATH}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
