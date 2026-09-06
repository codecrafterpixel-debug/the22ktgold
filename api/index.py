import sys
from pathlib import Path

# Add project root and backend folder to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "backend"))

from backend.server import app, init_db

# Initialize database on cold start
init_db()

# Vercel WSGI entry point
# `app` is the Flask WSGI callable
