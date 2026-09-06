#!/usr/bin/env python3
"""
backend/server.py — THE 22KT GOLD | Python Flask & SQLite Backend Server
Provides full API endpoints for Admin Dashboard, Public APIs, Gold Rates, Authentication,
and Static Web Hosting with a self-contained SQLite database.
"""

import os
import re
import sys
import time
import json
import base64
import sqlite3
import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS
import jwt
import bcrypt
import requests

# ── Paths & Setup ──
import shutil

BASE_DIR = Path(__file__).resolve().parent.parent

if os.environ.get("VERCEL"):
    DB_PATH = Path("/tmp/the22ktgold.db")
    if not DB_PATH.exists():
        src_db = BASE_DIR / "the22ktgold.db"
        if src_db.exists():
            shutil.copyfile(src_db, DB_PATH)
    UPLOADS_DIR = Path("/tmp/uploads")
    IMAGES_DIR = Path("/tmp/images")
else:
    DB_PATH = BASE_DIR / "the22ktgold.db"
    UPLOADS_DIR = BASE_DIR / "uploads"
    IMAGES_DIR = BASE_DIR / "images"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder=str(BASE_DIR))
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

JWT_SECRET = os.environ.get("JWT_SECRET", "the22ktgold_secure_jwt_secret_key_2026")
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_HOURS = 12

# ── Database Connection & Initialization ──
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(str(DB_PATH), timeout=20.0)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'ADMIN' CHECK(role IN ('ADMIN', 'SUPER_ADMIN')),
        status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'DISABLED')),
        last_login TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS admin_access_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER REFERENCES admins(id) ON DELETE SET NULL,
        admin_email TEXT,
        action TEXT NOT NULL,
        module TEXT NOT NULL,
        ip_address TEXT,
        user_agent TEXT,
        status TEXT NOT NULL DEFAULT 'SUCCESS',
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS site_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        setting_key TEXT NOT NULL UNIQUE,
        setting_value TEXT,
        updated_by INTEGER REFERENCES admins(id) ON DELETE SET NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        phone TEXT,
        status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'DISABLED')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        slug TEXT NOT NULL UNIQUE,
        description TEXT,
        image TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        slug TEXT NOT NULL UNIQUE,
        category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
        description TEXT,
        purity INTEGER NOT NULL DEFAULT 22,
        weight REAL NOT NULL DEFAULT 0,
        making_charges REAL NOT NULL DEFAULT 0,
        base_price REAL NOT NULL DEFAULT 0,
        current_price REAL NOT NULL DEFAULT 0,
        stock INTEGER NOT NULL DEFAULT 0,
        sku TEXT UNIQUE,
        featured INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS product_images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
        image_url TEXT NOT NULL,
        is_primary INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_number TEXT NOT NULL UNIQUE,
        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        customer_name TEXT NOT NULL,
        customer_phone TEXT,
        customer_email TEXT,
        address TEXT,
        product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
        product_name TEXT NOT NULL,
        product_image TEXT,
        quantity INTEGER NOT NULL DEFAULT 1,
        weight REAL NOT NULL DEFAULT 0,
        purity INTEGER NOT NULL DEFAULT 22,
        gold_rate_used REAL NOT NULL DEFAULT 0,
        making_charges REAL NOT NULL DEFAULT 0,
        gst REAL NOT NULL DEFAULT 0,
        discount REAL NOT NULL DEFAULT 0,
        total_amount REAL NOT NULL DEFAULT 0,
        payment_status TEXT NOT NULL DEFAULT 'Pending',
        order_status TEXT NOT NULL DEFAULT 'Pending Payment',
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
        name TEXT NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        weight REAL NOT NULL DEFAULT 0,
        price REAL NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS gold_rates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rate_22k REAL NOT NULL,
        rate_24k REAL NOT NULL,
        rate_18k REAL NOT NULL,
        source TEXT NOT NULL DEFAULT 'API',
        is_manual INTEGER NOT NULL DEFAULT 0,
        manual_22k REAL,
        manual_24k REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS gold_rate_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rate_22k REAL NOT NULL,
        rate_24k REAL NOT NULL,
        rate_18k REAL NOT NULL,
        change_amount REAL NOT NULL DEFAULT 0,
        change_percent REAL NOT NULL DEFAULT 0,
        source TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS enquiries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        email TEXT,
        message TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'New',
        admin_notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS custom_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        email TEXT,
        jewellery_type TEXT NOT NULL,
        description TEXT NOT NULL,
        weight REAL,
        purity INTEGER,
        budget REAL,
        reference_image TEXT,
        status TEXT NOT NULL DEFAULT 'New',
        quote_amount REAL,
        admin_notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS gallery (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        alt_text TEXT,
        image_url TEXT NOT NULL,
        category TEXT,
        featured INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # ── Default Admin Seeding ──
    cursor.execute("SELECT COUNT(*) FROM admins")
    if cursor.fetchone()[0] == 0:
        h_super = bcrypt.hashpw(b"Yash2112", bcrypt.gensalt(12)).decode("utf-8")
        h_admin = bcrypt.hashpw(b"Veer@2112", bcrypt.gensalt(12)).decode("utf-8")
        cursor.execute(
            "INSERT INTO admins (name, email, password_hash, role, status) VALUES (?, ?, ?, ?, ?)",
            ("Yash Panchal", "22ktgold@yashpanchal.com", h_super, "SUPER_ADMIN", "ACTIVE")
        )
        cursor.execute(
            "INSERT INTO admins (name, email, password_hash, role, status) VALUES (?, ?, ?, ?, ?)",
            ("Veer Shah", "22ktgold@veershah.com", h_admin, "ADMIN", "ACTIVE")
        )

    # ── Default Categories Seeding ──
    cursor.execute("SELECT COUNT(*) FROM categories")
    if cursor.fetchone()[0] == 0:
        cats = [
            ('Rings', 'rings', 'Handcrafted 22KT gold rings for every occasion.', 'images/cat-rings.jpg', 1),
            ('Necklaces', 'necklaces', 'Elegant gold necklaces and chains.', 'images/cat-necklaces.jpg', 1),
            ('Bangles', 'bangles', 'Timeless gold bangles and kadas.', 'images/cat-bangles.jpg', 1),
            ('Earrings', 'earrings', 'Delicate and statement gold earrings.', 'images/cat-earrings.jpg', 1),
            ('Bridal Sets', 'bridal-sets', 'Complete bridal jewellery collections.', 'images/cat-bridal.jpg', 1),
            ("Men's Gold", 'mens-gold', 'Masculine gold chains, bracelets and accessories.', 'images/cat-mens.jpg', 1)
        ]
        cursor.executemany("INSERT INTO categories (name, slug, description, image, active) VALUES (?, ?, ?, ?, ?)", cats)

    # ── Default Products Seeding ──
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        prods = [
            ('Heritage Gold Ring', 'heritage-gold-ring', 1, 'Intricately hand-crafted 22KT gold ring with fine filigree detailing.', 22, 4.200, 500, 31000, 33500, 10, 'SKU-001', 1, 1),
            ('Royal Bridal Necklace', 'royal-bridal-necklace', 5, 'Traditional bridal masterpiece handcrafted for your grand wedding.', 22, 48.500, 5000, 350000, 375000, 3, 'SKU-002', 1, 1),
            ('Temple Gold Bangles', 'temple-gold-bangles', 3, 'Timeless antique finished 22KT bangles and kadas crafted to perfection.', 22, 32.000, 3000, 235000, 250000, 5, 'SKU-003', 1, 1),
            ("Classic Men's Chain", 'classic-mens-chain', 6, 'Durable and elegant 22KT machine-cut & hand-linked gold chain.', 22, 18.300, 2000, 135000, 142000, 8, 'SKU-004', 0, 1)
        ]
        cursor.executemany("""
            INSERT INTO products (name, slug, category_id, description, purity, weight, making_charges, base_price, current_price, stock, sku, featured, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, prods)

    # ── Default Site Settings ──
    cursor.execute("SELECT COUNT(*) FROM site_settings")
    if cursor.fetchone()[0] == 0:
        settings = [
            ('business_name', 'THE 22KT GOLD'),
            ('business_email', 'info@the22ktgold.com'),
            ('business_phone', '+91 98765 00000'),
            ('business_whatsapp', '+91 98765 00000'),
            ('business_address', 'Shop No. 1, Gold Market, Jewellers Street, Mumbai - 400001'),
            ('business_hours', 'Mon–Sat: 10:00 AM – 8:00 PM, Sun: 11:00 AM – 6:00 PM'),
            ('website_title', 'THE 22KT GOLD — Premium 22KT Gold Jewellery'),
            ('meta_description', 'Handcrafted 22KT gold jewellery. Custom orders, bridal sets, rings, necklaces and more.'),
            ('default_currency', 'INR'),
            ('default_country', 'India'),
            ('timezone', 'Asia/Kolkata'),
            ('contact_email', 'contact@the22ktgold.com'),
            ('support_phone', '+91 98765 00001'),
            ('instagram', 'https://instagram.com/the22ktgold'),
            ('facebook', 'https://facebook.com/the22ktgold'),
            ('footer_text', 'Crafted with love. Hallmarked for purity.'),
            ('copyright_text', '© 2026 THE 22KT GOLD. All rights reserved.'),
            ('gold_is_manual', '0'),
            ('gold_manual_22k', '7250'),
            ('gold_manual_24k', '7910')
        ]
        cursor.executemany("INSERT INTO site_settings (setting_key, setting_value) VALUES (?, ?)", settings)

    conn.commit()
    conn.close()

# Initialize DB on load
init_db()

# ── Helper Utilities ──
def make_slug(s):
    s = s.lower().strip()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'\s+', '-', s)
    return re.sub(r'-+', '-', s)

def dict_from_row(row):
    return dict(row) if row else None

def list_from_rows(rows):
    return [dict(r) for r in rows]

def sign_token(admin_dict):
    payload = {
        "id": admin_dict["id"],
        "email": admin_dict["email"],
        "role": admin_dict["role"],
        "name": admin_dict["name"],
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=JWT_EXPIRES_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def log_action(admin_id, admin_email, action, module, status="SUCCESS", notes=None):
    try:
        ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        ua = request.headers.get("User-Agent")
        db = get_db()
        db.execute(
            "INSERT INTO admin_access_logs (admin_id, admin_email, action, module, ip_address, user_agent, status, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (admin_id, admin_email, action, module, ip, ua, status, notes)
        )
        db.commit()
    except Exception as e:
        print(f"Log action error: {e}", file=sys.stderr)

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Unauthorized — no token provided"}), 401
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            db = get_db()
            cursor = db.execute("SELECT id, name, email, role, status FROM admins WHERE id = ?", (payload["id"],))
            admin = cursor.fetchone()
            if not admin or admin["status"] == "DISABLED":
                return jsonify({"error": "Account is disabled or not found"}), 401
            g.current_admin = dict(admin)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except Exception:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated

def require_super_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not hasattr(g, "current_admin") or g.current_admin.get("role") != "SUPER_ADMIN":
            return jsonify({"error": "Forbidden — Super Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated

# ── Live Gold Rate Calculation ──
cached_gold_data = None
last_gold_fetch = 0
GOLD_CACHE_TTL = 60

def fetch_live_gold_rates():
    global cached_gold_data, last_gold_fetch
    now = time.time()
    if cached_gold_data and (now - last_gold_fetch) < GOLD_CACHE_TTL:
        return cached_gold_data

    api_key = os.environ.get("GOLD_API_KEY")
    rate_24k = 0
    change_24k = 0
    change_percent = 0
    provider = "Spot Bullion Feed"

    if api_key:
        try:
            r = requests.get("https://www.goldapi.io/api/XAU/INR", headers={"x-access-token": api_key, "Content-Type": "application/json"}, timeout=5)
            if r.status_code == 200:
                data = r.json()
                rate_24k = data.get("price_gram_24k") or (data.get("price", 0) / 31.1034768)
                prev = data.get("prev_close_price", 0) / 31.1034768 if data.get("prev_close_price") else rate_24k
                change_24k = (data.get("ch") / 31.1034768) if data.get("ch") is not None else (rate_24k - prev)
                change_percent = data.get("chp") or ((change_24k / prev * 100) if prev > 0 else 0)
                provider = "GoldAPI.io (Live XAU/INR)"
        except Exception:
            pass

    if not rate_24k:
        try:
            r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=pax-gold&vs_currencies=inr&include_24hr_change=true", timeout=5)
            if r.status_code == 200:
                data = r.json()
                paxg = data.get("pax-gold", {}).get("inr", 0)
                if paxg > 0:
                    rate_24k = paxg / 31.1034768
                    change_percent = data.get("pax-gold", {}).get("inr_24h_change", 0)
                    change_24k = rate_24k * (change_percent / 100)
                    provider = "Spot Bullion Feed"
        except Exception:
            pass

    if not rate_24k:
        rate_24k = 7350.0
        change_24k = 0.0
        change_percent = 0.0
        provider = "Market Indicative Rate"

    rate_22k = rate_24k * (22.0 / 24.0)
    rate_18k = rate_24k * (18.0 / 24.0)
    change_22k = change_24k * (22.0 / 24.0)
    change_18k = change_24k * (18.0 / 24.0)

    cached_gold_data = {
        "rate24k": round(rate_24k, 2),
        "rate22k": round(rate_22k, 2),
        "rate18k": round(rate_18k, 2),
        "change24k": round(change_24k, 2),
        "change22k": round(change_22k, 2),
        "change18k": round(change_18k, 2),
        "changePercent": round(change_percent, 3),
        "provider": provider,
        "fetchedAt": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    last_gold_fetch = now
    return cached_gold_data

# ══════════════════════════════════════════════════════════════════
# AUTH ROUTES
# ══════════════════════════════════════════════════════════════════
@app.route("/api/admin/auth/login", methods=["POST"])
@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json(silent=True) or request.form.to_dict()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    db = get_db()
    cursor = db.execute("SELECT * FROM admins WHERE email = ?", (email,))
    admin = cursor.fetchone()

    if not admin:
        log_action(None, email, "LOGIN", "Auth", "FAILURE", "Admin not found")
        return jsonify({"error": "Invalid credentials"}), 401

    if admin["status"] == "DISABLED":
        log_action(admin["id"], admin["email"], "LOGIN", "Auth", "FAILURE", "Account disabled")
        return jsonify({"error": "Your account has been disabled. Contact Super Admin."}), 401

    try:
        valid = bcrypt.checkpw(password.encode("utf-8"), admin["password_hash"].encode("utf-8"))
    except Exception:
        valid = False

    if not valid:
        log_action(admin["id"], admin["email"], "LOGIN", "Auth", "FAILURE", "Wrong password")
        return jsonify({"error": "Invalid credentials"}), 401

    db.execute("UPDATE admins SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (admin["id"],))
    db.commit()

    admin_dict = dict(admin)
    token = sign_token(admin_dict)
    log_action(admin["id"], admin["email"], "LOGIN", "Auth", "SUCCESS")

    return jsonify({
        "token": token,
        "admin": {
            "id": admin["id"],
            "name": admin["name"],
            "email": admin["email"],
            "role": admin["role"]
        }
    })

@app.route("/api/admin/auth/logout", methods=["POST"])
@app.route("/api/admin/logout", methods=["POST"])
@require_auth
def admin_logout():
    log_action(g.current_admin["id"], g.current_admin["email"], "LOGOUT", "Auth")
    return jsonify({"success": True})

@app.route("/api/admin/auth/me", methods=["GET"])
@app.route("/api/admin/me", methods=["GET"])
@require_auth
def admin_me():
    return jsonify({
        "id": g.current_admin["id"],
        "name": g.current_admin["name"],
        "email": g.current_admin["email"],
        "role": g.current_admin["role"]
    })

# ══════════════════════════════════════════════════════════════════
# DASHBOARD STATS
# ══════════════════════════════════════════════════════════════════
@app.route("/api/admin/dashboard", methods=["GET"])
@require_auth
def admin_dashboard():
    db = get_db()
    total_orders = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    total_users = db.execute("SELECT COUNT(*) FROM users WHERE status = 'ACTIVE'").fetchone()[0]
    total_custom = db.execute("SELECT COUNT(*) FROM custom_orders WHERE status NOT IN ('Completed','Rejected')").fetchone()[0]
    total_enquiries = db.execute("SELECT COUNT(*) FROM enquiries WHERE status IN ('New','In Progress','Contacted')").fetchone()[0]

    recent_orders = list_from_rows(db.execute("""
        SELECT id, order_number, customer_name, product_name, weight, order_status, payment_status, created_at
        FROM orders
        ORDER BY created_at DESC LIMIT 10
    """).fetchall())

    return jsonify({
        "stats": {
            "totalOrders": total_orders,
            "registeredUsers": total_users,
            "customRequests": total_custom,
            "openEnquiries": total_enquiries
        },
        "recentOrders": recent_orders
    })

# ══════════════════════════════════════════════════════════════════
# PRODUCTS CRUD
# ══════════════════════════════════════════════════════════════════
@app.route("/api/admin/products", methods=["GET"])
@require_auth
def admin_get_products():
    page = max(1, int(request.args.get("page", 1)))
    limit = min(100, int(request.args.get("limit", 20)))
    offset = (page - 1) * limit
    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()
    active = request.args.get("active")
    featured = request.args.get("featured")

    where = ["1=1"]
    params = []

    if search:
        where.append("(p.name LIKE ? OR p.sku LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if category:
        where.append("p.category_id = ?")
        params.append(category)
    if active is not None and active != "":
        where.append("p.active = ?")
        params.append(1 if active in ["1", "true", True] else 0)
    if featured is not None and featured != "":
        where.append("p.featured = ?")
        params.append(1 if featured in ["1", "true", True] else 0)

    where_str = " AND ".join(where)
    db = get_db()
    total = db.execute(f"SELECT COUNT(*) FROM products p WHERE {where_str}", params).fetchone()[0]

    query_params = list(params) + [limit, offset]
    rows = db.execute(f"""
        SELECT p.*, c.name as category_name,
               (SELECT image_url FROM product_images pi WHERE pi.product_id = p.id AND pi.is_primary = 1 LIMIT 1) as primary_image
        FROM products p
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE {where_str}
        ORDER BY p.created_at DESC
        LIMIT ? OFFSET ?
    """, query_params).fetchall()

    return jsonify({
        "products": list_from_rows(rows),
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if limit > 0 else 1
    })

@app.route("/api/admin/products/<int:id>", methods=["GET"])
@require_auth
def admin_get_product(id):
    db = get_db()
    product = db.execute("""
        SELECT p.*, c.name as category_name
        FROM products p LEFT JOIN categories c ON c.id = p.category_id
        WHERE p.id = ?
    """, (id,)).fetchone()
    if not product:
        return jsonify({"error": "Product not found"}), 404

    images = list_from_rows(db.execute("SELECT * FROM product_images WHERE product_id = ? ORDER BY is_primary DESC", (id,)).fetchall())
    res = dict(product)
    res["images"] = images
    return jsonify(res)

@app.route("/api/admin/products", methods=["POST"])
@require_auth
def admin_create_product():
    data = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    name = (data.get("name") or "").strip()
    category_id = data.get("category_id") or None
    description = data.get("description") or None
    purity = int(data.get("purity") or 22)
    weight = float(data.get("weight") or 0)
    making_charges = float(data.get("making_charges") or 0)
    base_price = float(data.get("base_price") or 0)
    current_price = float(data.get("current_price") or 0)
    stock = int(data.get("stock") or 0)
    sku = data.get("sku") or None
    featured = 1 if str(data.get("featured")).lower() in ["true", "1"] else 0
    active = 0 if str(data.get("active")).lower() in ["false", "0"] else 1

    if not name:
        return jsonify({"error": "Product name is required"}), 400

    slug = make_slug(name)
    db = get_db()
    exists = db.execute("SELECT id FROM products WHERE slug = ?", (slug,)).fetchone()
    if exists:
        return jsonify({"error": "A product with this name already exists"}), 400

    cursor = db.execute("""
        INSERT INTO products (name, slug, category_id, description, purity, weight, making_charges, base_price, current_price, stock, sku, featured, active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, slug, category_id, description, purity, weight, making_charges, base_price, current_price, stock, sku, featured, active))
    product_id = cursor.lastrowid

    # Handle image file upload or base64
    image_file = request.files.get("image")
    if image_file and image_file.filename:
        ext = Path(image_file.filename).suffix.lower()
        if ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
            b64_str = base64.b64encode(image_file.read()).decode("utf-8")
            mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else f"image/{ext.replace('.', '')}"
            img_url = f"data:{mime};base64,{b64_str}"
            db.execute("INSERT INTO product_images (product_id, image_url, is_primary) VALUES (?, ?, 1)", (product_id, img_url))
    elif data.get("image_url"):
        db.execute("INSERT INTO product_images (product_id, image_url, is_primary) VALUES (?, ?, 1)", (product_id, data.get("image_url")))

    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "CREATE_PRODUCT", "Products")

    created = dict(db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone())
    return jsonify(created), 201

@app.route("/api/admin/products/<int:id>", methods=["PUT"])
@require_auth
def admin_update_product(id):
    data = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    db = get_db()
    check = db.execute("SELECT * FROM products WHERE id = ?", (id,)).fetchone()
    if not check:
        return jsonify({"error": "Product not found"}), 404

    name = (data.get("name") or check["name"]).strip()
    slug = make_slug(name)
    category_id = data.get("category_id", check["category_id"])
    description = data.get("description", check["description"])
    purity = int(data.get("purity", check["purity"]))
    weight = float(data.get("weight", check["weight"]))
    making_charges = float(data.get("making_charges", check["making_charges"]))
    base_price = float(data.get("base_price", check["base_price"]))
    current_price = float(data.get("current_price", check["current_price"]))
    stock = int(data.get("stock", check["stock"]))
    sku = data.get("sku", check["sku"])
    featured = 1 if str(data.get("featured", check["featured"])).lower() in ["true", "1"] else 0
    active = 0 if str(data.get("active", check["active"])).lower() in ["false", "0"] else 1

    db.execute("""
        UPDATE products SET name=?, slug=?, category_id=?, description=?, purity=?, weight=?, making_charges=?,
        base_price=?, current_price=?, stock=?, sku=?, featured=?, active=?, updated_at=CURRENT_TIMESTAMP WHERE id=?
    """, (name, slug, category_id, description, purity, weight, making_charges, base_price, current_price, stock, sku, featured, active, id))

    image_file = request.files.get("image")
    if image_file and image_file.filename:
        ext = Path(image_file.filename).suffix.lower()
        if ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
            b64_str = base64.b64encode(image_file.read()).decode("utf-8")
            mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else f"image/{ext.replace('.', '')}"
            img_url = f"data:{mime};base64,{b64_str}"
            db.execute("UPDATE product_images SET is_primary = 0 WHERE product_id = ?", (id,))
            db.execute("INSERT INTO product_images (product_id, image_url, is_primary) VALUES (?, ?, 1)", (id, img_url))

    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "UPDATE_PRODUCT", "Products")
    updated = dict(db.execute("SELECT * FROM products WHERE id = ?", (id,)).fetchone())
    return jsonify(updated)

@app.route("/api/admin/products/<int:id>", methods=["DELETE"])
@require_auth
def admin_delete_product(id):
    db = get_db()
    check = db.execute("SELECT id FROM products WHERE id = ?", (id,)).fetchone()
    if not check:
        return jsonify({"error": "Product not found"}), 404
    db.execute("DELETE FROM product_images WHERE product_id = ?", (id,))
    db.execute("DELETE FROM products WHERE id = ?", (id,))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "DELETE_PRODUCT", "Products")
    return jsonify({"success": True})

# ══════════════════════════════════════════════════════════════════
# PUBLIC PRODUCTS API
# ══════════════════════════════════════════════════════════════════
@app.route("/api/products", methods=["GET", "POST", "DELETE"])
def public_products():
    db = get_db()
    if request.method == "GET":
        rows = db.execute("""
            SELECT p.*, c.name as category_name,
                   (SELECT image_url FROM product_images pi WHERE pi.product_id = p.id AND pi.is_primary = 1 LIMIT 1) as image
            FROM products p
            LEFT JOIN categories c ON c.id = p.category_id
            WHERE p.active = 1
            ORDER BY p.featured DESC, p.created_at DESC
        """).fetchall()
        return jsonify(list_from_rows(rows))

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Name required"}), 400
        slug = make_slug(name)
        weight = float(data.get("weight", 0))
        price = float(data.get("price", data.get("current_price", 0)))
        image = data.get("image", "")

        cursor = db.execute("""
            INSERT INTO products (name, slug, weight, current_price, active)
            VALUES (?, ?, ?, ?, 1)
        """, (name, slug, weight, price))
        pid = cursor.lastrowid
        if image:
            db.execute("INSERT INTO product_images (product_id, image_url, is_primary) VALUES (?, ?, 1)", (pid, image))
        db.commit()
        return jsonify({"id": pid, "name": name, "slug": slug}), 201

    if request.method == "DELETE":
        pid = request.args.get("id")
        if pid:
            db.execute("UPDATE products SET active = 0 WHERE id = ? OR sku = ?", (pid, pid))
            db.commit()
            return jsonify({"success": True})
        return jsonify({"error": "Missing id"}), 400

# ══════════════════════════════════════════════════════════════════
# CATEGORIES CRUD
# ══════════════════════════════════════════════════════════════════
@app.route("/api/admin/categories", methods=["GET"])
@require_auth
def admin_get_categories():
    search = request.args.get("search", "").strip()
    db = get_db()
    where = ["1=1"]
    params = []
    if search:
        where.append("c.name LIKE ?")
        params.append(f"%{search}%")

    rows = db.execute(f"""
        SELECT c.*, COUNT(p.id) as product_count
        FROM categories c
        LEFT JOIN products p ON p.category_id = c.id AND p.active = 1
        WHERE {" AND ".join(where)}
        GROUP BY c.id
        ORDER BY c.name ASC
    """, params).fetchall()
    return jsonify(list_from_rows(rows))

@app.route("/api/admin/categories", methods=["POST"])
@require_auth
def admin_create_category():
    data = request.get_json(silent=True) or request.form.to_dict()
    name = (data.get("name") or "").strip()
    description = data.get("description")
    image = data.get("image")
    active = 1 if data.get("active") not in [False, "false", "0", 0] else 0

    if not name:
        return jsonify({"error": "Category name is required"}), 400

    slug = make_slug(name)
    db = get_db()
    exists = db.execute("SELECT id FROM categories WHERE slug = ?", (slug,)).fetchone()
    if exists:
        return jsonify({"error": "A category with this name already exists"}), 400

    cursor = db.execute(
        "INSERT INTO categories (name, slug, description, image, active) VALUES (?, ?, ?, ?, ?)",
        (name, slug, description, image, active)
    )
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "CREATE_CATEGORY", "Categories")
    created = dict(db.execute("SELECT * FROM categories WHERE id = ?", (cursor.lastrowid,)).fetchone())
    return jsonify(created), 201

@app.route("/api/admin/categories/<int:id>", methods=["PUT"])
@require_auth
def admin_update_category(id):
    data = request.get_json(silent=True) or request.form.to_dict()
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Category name is required"}), 400

    slug = make_slug(name)
    description = data.get("description")
    image = data.get("image")
    active = 1 if data.get("active") not in [False, "false", "0", 0] else 0

    db = get_db()
    check = db.execute("SELECT id FROM categories WHERE id = ?", (id,)).fetchone()
    if not check:
        return jsonify({"error": "Category not found"}), 404

    db.execute(
        "UPDATE categories SET name=?, slug=?, description=?, image=?, active=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (name, slug, description, image, active, id)
    )
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "UPDATE_CATEGORY", "Categories")
    updated = dict(db.execute("SELECT * FROM categories WHERE id = ?", (id,)).fetchone())
    return jsonify(updated)

@app.route("/api/admin/categories/<int:id>", methods=["DELETE"])
@require_auth
def admin_delete_category(id):
    db = get_db()
    cnt = db.execute("SELECT COUNT(*) FROM products WHERE category_id = ?", (id,)).fetchone()[0]
    if cnt > 0:
        return jsonify({"error": f"Cannot delete: {cnt} product(s) belong to this category. Reassign them first."}), 400
    db.execute("DELETE FROM categories WHERE id = ?", (id,))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "DELETE_CATEGORY", "Categories")
    return jsonify({"success": True})

# ══════════════════════════════════════════════════════════════════
# ORDERS CRUD
# ══════════════════════════════════════════════════════════════════
@app.route("/api/admin/orders", methods=["GET"])
@require_auth
def admin_get_orders():
    page = max(1, int(request.args.get("page", 1)))
    limit = min(100, int(request.args.get("limit", 20)))
    offset = (page - 1) * limit
    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip()
    payment = request.args.get("payment", "").strip()
    date_from = request.args.get("dateFrom", "").strip()
    date_to = request.args.get("dateTo", "").strip()
    sort_col = request.args.get("sort", "created_at")
    if sort_col not in ["created_at", "total_amount", "customer_name"]:
        sort_col = "created_at"
    dir_str = "ASC" if request.args.get("dir") == "asc" else "DESC"

    where = ["1=1"]
    params = []
    if search:
        where.append("(order_number LIKE ? OR customer_name LIKE ? OR customer_email LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    if status:
        where.append("order_status = ?")
        params.append(status)
    if payment:
        where.append("payment_status = ?")
        params.append(payment)
    if date_from:
        where.append("DATE(created_at) >= ?")
        params.append(date_from)
    if date_to:
        where.append("DATE(created_at) <= ?")
        params.append(date_to)

    where_str = " AND ".join(where)
    db = get_db()
    total = db.execute(f"SELECT COUNT(*) FROM orders WHERE {where_str}", params).fetchone()[0]

    rows = db.execute(f"""
        SELECT * FROM orders WHERE {where_str} ORDER BY {sort_col} {dir_str} LIMIT ? OFFSET ?
    """, list(params) + [limit, offset]).fetchall()

    return jsonify({
        "orders": list_from_rows(rows),
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if limit > 0 else 1
    })

@app.route("/api/admin/orders/<int:id>", methods=["GET"])
@require_auth
def admin_get_order(id):
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id = ?", (id,)).fetchone()
    if not order:
        return jsonify({"error": "Order not found"}), 404
    return jsonify(dict(order))

@app.route("/api/admin/orders/<int:id>", methods=["PATCH"])
@require_auth
def admin_update_order(id):
    data = request.get_json(silent=True) or {}
    db = get_db()
    check = db.execute("SELECT id FROM orders WHERE id = ?", (id,)).fetchone()
    if not check:
        return jsonify({"error": "Order not found"}), 404

    updates = []
    params = []
    if "order_status" in data:
        updates.append("order_status = ?")
        params.append(data["order_status"])
    if "payment_status" in data:
        updates.append("payment_status = ?")
        params.append(data["payment_status"])
    if "notes" in data:
        updates.append("notes = ?")
        params.append(data["notes"])

    if not updates:
        return jsonify({"error": "Nothing to update"}), 400

    params.append(id)
    db.execute(f"UPDATE orders SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", params)
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "UPDATE_ORDER", "Orders")
    updated = dict(db.execute("SELECT * FROM orders WHERE id = ?", (id,)).fetchone())
    return jsonify(updated)

@app.route("/api/admin/orders/<int:id>", methods=["DELETE"])
@require_auth
def admin_cancel_order(id):
    db = get_db()
    db.execute("UPDATE orders SET order_status = 'Cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (id,))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "CANCEL_ORDER", "Orders")
    return jsonify({"success": True})

@app.route("/api/orders", methods=["POST"])
def public_create_order():
    data = request.get_json(silent=True) or {}
    name = (data.get("customer_name") or data.get("name") or "").strip()
    phone = data.get("customer_phone") or data.get("phone")
    email = data.get("customer_email") or data.get("email")
    address = data.get("address")
    product_name = data.get("product_name", "Gold Jewellery")
    weight = float(data.get("weight", 0))
    total_amount = float(data.get("total_amount", 0))

    if not name:
        return jsonify({"error": "Customer name is required"}), 400

    order_num = f"ORD-{int(time.time())}-{datetime.date.today().strftime('%y%m%d')}"
    db = get_db()
    cursor = db.execute("""
        INSERT INTO orders (order_number, customer_name, customer_phone, customer_email, address, product_name, weight, total_amount)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (order_num, name, phone, email, address, product_name, weight, total_amount))
    db.commit()
    return jsonify({"success": True, "order_number": order_num, "id": cursor.lastrowid}), 201

# ══════════════════════════════════════════════════════════════════
# CUSTOM ORDERS CRUD
# ══════════════════════════════════════════════════════════════════
@app.route("/api/admin/custom-orders", methods=["GET"])
@require_auth
def admin_get_custom_orders():
    page = max(1, int(request.args.get("page", 1)))
    limit = min(100, int(request.args.get("limit", 20)))
    offset = (page - 1) * limit
    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip()

    where = ["1=1"]
    params = []
    if search:
        where.append("(name LIKE ? OR email LIKE ? OR jewellery_type LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    if status:
        where.append("status = ?")
        params.append(status)

    where_str = " AND ".join(where)
    db = get_db()
    total = db.execute(f"SELECT COUNT(*) FROM custom_orders WHERE {where_str}", params).fetchone()[0]
    rows = db.execute(f"SELECT * FROM custom_orders WHERE {where_str} ORDER BY created_at DESC LIMIT ? OFFSET ?", list(params) + [limit, offset]).fetchall()

    return jsonify({
        "customOrders": list_from_rows(rows),
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if limit > 0 else 1
    })

@app.route("/api/admin/custom-orders/<int:id>", methods=["GET"])
@require_auth
def admin_get_custom_order(id):
    db = get_db()
    item = db.execute("SELECT * FROM custom_orders WHERE id = ?", (id,)).fetchone()
    if not item:
        return jsonify({"error": "Custom order not found"}), 404
    return jsonify(dict(item))

@app.route("/api/admin/custom-orders/<int:id>", methods=["PATCH"])
@require_auth
def admin_update_custom_order(id):
    data = request.get_json(silent=True) or {}
    db = get_db()
    updates = []
    params = []
    if "status" in data:
        updates.append("status = ?")
        params.append(data["status"])
    if "admin_notes" in data:
        updates.append("admin_notes = ?")
        params.append(data["admin_notes"])
    if "quote_amount" in data:
        updates.append("quote_amount = ?")
        params.append(float(data["quote_amount"]))

    if not updates:
        return jsonify({"error": "Nothing to update"}), 400

    params.append(id)
    db.execute(f"UPDATE custom_orders SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", params)
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "UPDATE_CUSTOM_ORDER", "Custom Orders")
    updated = dict(db.execute("SELECT * FROM custom_orders WHERE id = ?", (id,)).fetchone())
    return jsonify(updated)

@app.route("/api/admin/custom-orders/<int:id>", methods=["DELETE"])
@require_auth
def admin_reject_custom_order(id):
    db = get_db()
    db.execute("UPDATE custom_orders SET status = 'Rejected', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (id,))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "REJECT_CUSTOM_ORDER", "Custom Orders")
    return jsonify({"success": True})

@app.route("/api/custom-orders", methods=["POST"])
def public_create_custom_order():
    data = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    name = (data.get("name") or "").strip()
    phone = data.get("phone")
    email = data.get("email")
    jewellery_type = data.get("jewellery_type") or data.get("type", "Custom Piece")
    description = data.get("description", "")
    weight = float(data.get("weight")) if data.get("weight") else None
    purity = int(data.get("purity")) if data.get("purity") else 22
    budget = float(data.get("budget")) if data.get("budget") else None

    if not name:
        return jsonify({"error": "Name is required"}), 400

    ref_img = None
    image_file = request.files.get("reference_image") or request.files.get("image")
    if image_file and image_file.filename:
        ext = Path(image_file.filename).suffix.lower()
        b64_str = base64.b64encode(image_file.read()).decode("utf-8")
        mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else f"image/{ext.replace('.', '')}"
        ref_img = f"data:{mime};base64,{b64_str}"

    db = get_db()
    cursor = db.execute("""
        INSERT INTO custom_orders (name, phone, email, jewellery_type, description, weight, purity, budget, reference_image)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, phone, email, jewellery_type, description, weight, purity, budget, ref_img))
    db.commit()
    return jsonify({"success": True, "id": cursor.lastrowid}), 201

# ══════════════════════════════════════════════════════════════════
# ENQUIRIES CRUD
# ══════════════════════════════════════════════════════════════════
@app.route("/api/admin/enquiries", methods=["GET"])
@require_auth
def admin_get_enquiries():
    page = max(1, int(request.args.get("page", 1)))
    limit = min(100, int(request.args.get("limit", 20)))
    offset = (page - 1) * limit
    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip()

    where = ["1=1"]
    params = []
    if search:
        where.append("(name LIKE ? OR email LIKE ? OR phone LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    if status:
        where.append("status = ?")
        params.append(status)

    where_str = " AND ".join(where)
    db = get_db()
    total = db.execute(f"SELECT COUNT(*) FROM enquiries WHERE {where_str}", params).fetchone()[0]
    rows = db.execute(f"SELECT * FROM enquiries WHERE {where_str} ORDER BY created_at DESC LIMIT ? OFFSET ?", list(params) + [limit, offset]).fetchall()

    return jsonify({
        "enquiries": list_from_rows(rows),
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if limit > 0 else 1
    })

@app.route("/api/admin/enquiries/<int:id>", methods=["GET"])
@require_auth
def admin_get_enquiry(id):
    db = get_db()
    item = db.execute("SELECT * FROM enquiries WHERE id = ?", (id,)).fetchone()
    if not item:
        return jsonify({"error": "Enquiry not found"}), 404
    return jsonify(dict(item))

@app.route("/api/admin/enquiries/<int:id>", methods=["PATCH"])
@require_auth
def admin_update_enquiry(id):
    data = request.get_json(silent=True) or {}
    db = get_db()
    updates = []
    params = []
    if "status" in data:
        updates.append("status = ?")
        params.append(data["status"])
    if "admin_notes" in data:
        updates.append("admin_notes = ?")
        params.append(data["admin_notes"])

    if not updates:
        return jsonify({"error": "Nothing to update"}), 400

    params.append(id)
    db.execute(f"UPDATE enquiries SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", params)
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "UPDATE_ENQUIRY", "Enquiries")
    updated = dict(db.execute("SELECT * FROM enquiries WHERE id = ?", (id,)).fetchone())
    return jsonify(updated)

@app.route("/api/admin/enquiries/<int:id>", methods=["DELETE"])
@require_auth
def admin_delete_enquiry(id):
    db = get_db()
    db.execute("DELETE FROM enquiries WHERE id = ?", (id,))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "DELETE_ENQUIRY", "Enquiries")
    return jsonify({"success": True})

@app.route("/api/enquiries", methods=["POST"])
def public_create_enquiry():
    data = request.get_json(silent=True) or request.form.to_dict()
    name = (data.get("name") or "").strip()
    phone = data.get("phone")
    email = data.get("email")
    message = data.get("message") or ""

    if not name:
        return jsonify({"error": "Name is required"}), 400

    db = get_db()
    cursor = db.execute(
        "INSERT INTO enquiries (name, phone, email, message) VALUES (?, ?, ?, ?)",
        (name, phone, email, message)
    )
    db.commit()
    return jsonify({"success": True, "id": cursor.lastrowid}), 201

# ══════════════════════════════════════════════════════════════════
# GALLERY CRUD
# ══════════════════════════════════════════════════════════════════
@app.route("/api/admin/gallery", methods=["GET"])
@app.route("/api/gallery", methods=["GET"])
def get_gallery():
    page = max(1, int(request.args.get("page", 1)))
    limit = min(100, int(request.args.get("limit", 24)))
    offset = (page - 1) * limit
    category = request.args.get("category", "").strip()
    featured = request.args.get("featured")

    where = ["1=1"]
    params = []
    if category:
        where.append("category = ?")
        params.append(category)
    if featured is not None and featured != "":
        where.append("featured = ?")
        params.append(1 if featured in ["1", "true", True] else 0)

    where_str = " AND ".join(where)
    db = get_db()
    total = db.execute(f"SELECT COUNT(*) FROM gallery WHERE {where_str}", params).fetchone()[0]
    rows = db.execute(f"SELECT * FROM gallery WHERE {where_str} ORDER BY created_at DESC LIMIT ? OFFSET ?", list(params) + [limit, offset]).fetchall()

    return jsonify({
        "items": list_from_rows(rows),
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if limit > 0 else 1
    })

@app.route("/api/admin/gallery", methods=["POST"])
@require_auth
def admin_upload_gallery():
    data = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    title = (data.get("title") or "Gallery Image").strip()
    alt_text = data.get("alt_text")
    category = data.get("category")
    featured = 1 if str(data.get("featured")).lower() in ["true", "1"] else 0

    img_url = data.get("image_url")
    image_file = request.files.get("image")
    if image_file and image_file.filename:
        ext = Path(image_file.filename).suffix.lower()
        b64_str = base64.b64encode(image_file.read()).decode("utf-8")
        mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else f"image/{ext.replace('.', '')}"
        img_url = f"data:{mime};base64,{b64_str}"

    if not img_url:
        return jsonify({"error": "Image file is required"}), 400

    db = get_db()
    cursor = db.execute(
        "INSERT INTO gallery (title, alt_text, image_url, category, featured) VALUES (?, ?, ?, ?, ?)",
        (title, alt_text, img_url, category, featured)
    )
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "UPLOAD_GALLERY", "Gallery")
    item = dict(db.execute("SELECT * FROM gallery WHERE id = ?", (cursor.lastrowid,)).fetchone())
    return jsonify(item), 201

@app.route("/api/admin/gallery/<int:id>", methods=["PATCH"])
@require_auth
def admin_update_gallery(id):
    data = request.get_json(silent=True) or {}
    db = get_db()
    title = data.get("title")
    alt_text = data.get("alt_text")
    category = data.get("category")
    featured = 1 if data.get("featured") in [True, "true", 1, "1"] else 0

    db.execute(
        "UPDATE gallery SET title=?, alt_text=?, category=?, featured=? WHERE id=?",
        (title, alt_text, category, featured, id)
    )
    db.commit()
    updated = dict(db.execute("SELECT * FROM gallery WHERE id = ?", (id,)).fetchone())
    return jsonify(updated)

@app.route("/api/admin/gallery/<int:id>", methods=["DELETE"])
@require_auth
def admin_delete_gallery(id):
    db = get_db()
    db.execute("DELETE FROM gallery WHERE id = ?", (id,))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "DELETE_GALLERY", "Gallery")
    return jsonify({"success": True})

# ══════════════════════════════════════════════════════════════════
# GOLD RATES API
# ══════════════════════════════════════════════════════════════════
@app.route("/api/gold-rates", methods=["GET"])
def public_gold_rates():
    db = get_db()
    rows = db.execute("SELECT setting_key, setting_value FROM site_settings WHERE setting_key IN ('gold_is_manual','gold_manual_22k','gold_manual_24k')").fetchall()
    setting_map = {r["setting_key"]: r["setting_value"] for r in rows}

    if setting_map.get("gold_is_manual") == "1" and setting_map.get("gold_manual_22k"):
        rate_22k = float(setting_map["gold_manual_22k"])
        rate_24k = float(setting_map.get("gold_manual_24k") or (rate_22k * (24.0 / 22.0)))
        rate_18k = rate_24k * (18.0 / 24.0)
        provider = "Manual Admin Rate"
        change_24k = 0.0
        change_22k = 0.0
        change_18k = 0.0
        change_percent = 0.0
    else:
        live = fetch_live_gold_rates()
        rate_24k = live["rate24k"]
        rate_22k = live["rate22k"]
        rate_18k = live["rate18k"]
        change_24k = live["change24k"]
        change_22k = live["change22k"]
        change_18k = live["change18k"]
        change_percent = live["changePercent"]
        provider = live["provider"]

    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    formatted_time = now.strftime("%I:%M %p IST")

    return jsonify({
        "provider": provider,
        "updatedAt": now.isoformat(),
        "formattedTime": formatted_time,
        "gold": {
            "24k": {
                "perGram": round(rate_24k, 2),
                "per10g": round(rate_24k * 10, 2),
                "change": round(change_24k, 2),
                "changePercent": round(change_percent, 2)
            },
            "22k": {
                "perGram": round(rate_22k, 2),
                "per10g": round(rate_22k * 10, 2),
                "change": round(change_22k, 2),
                "changePercent": round(change_percent, 2)
            },
            "18k": {
                "perGram": round(rate_18k, 2),
                "per10g": round(rate_18k * 10, 2),
                "change": round(change_18k, 2),
                "changePercent": round(change_percent, 2)
            }
        }
    })

@app.route("/api/admin/gold-rates", methods=["GET"])
@require_auth
def admin_get_gold_rates():
    db = get_db()
    rows = db.execute("SELECT setting_key, setting_value FROM site_settings WHERE setting_key IN ('gold_is_manual','gold_manual_22k','gold_manual_24k')").fetchall()
    setting_map = {r["setting_key"]: r["setting_value"] for r in rows}

    live = fetch_live_gold_rates()
    if setting_map.get("gold_is_manual") == "1" and setting_map.get("gold_manual_22k"):
        m22k = float(setting_map["gold_manual_22k"])
        m24k = float(setting_map.get("gold_manual_24k") or (m22k * (24.0 / 22.0)))
        return jsonify({
            "isManual": True,
            "provider": "Manual Admin Rate",
            "rate22k": m22k,
            "rate24k": m24k,
            "rate18k": round(m24k * (18.0 / 24.0), 2),
            "change": 0,
            "changePercent": 0,
            "fetchedAt": datetime.datetime.now(datetime.timezone.utc).isoformat()
        })
    else:
        return jsonify({
            "isManual": False,
            "provider": live["provider"],
            "rate22k": live["rate22k"],
            "rate24k": live["rate24k"],
            "rate18k": live["rate18k"],
            "change": live["change22k"],
            "changePercent": live["changePercent"],
            "fetchedAt": live["fetchedAt"]
        })

@app.route("/api/admin/gold-rates/refresh", methods=["POST"])
@require_auth
def admin_refresh_gold_rates():
    global cached_gold_data, last_gold_fetch
    cached_gold_data = None
    last_gold_fetch = 0
    live = fetch_live_gold_rates()

    db = get_db()
    db.execute("""
        INSERT INTO gold_rate_history (rate_22k, rate_24k, rate_18k, change_amount, change_percent, source)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (live["rate22k"], live["rate24k"], live["rate18k"], live["change22k"], live["changePercent"], live["provider"]))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "REFRESH_GOLD_RATE", "Gold Rates")

    return jsonify({"success": True, **live})

@app.route("/api/admin/gold-rates/history", methods=["GET"])
@require_auth
def admin_gold_rates_history():
    limit = min(100, int(request.args.get("limit", 30)))
    db = get_db()
    rows = db.execute("SELECT * FROM gold_rate_history ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return jsonify(list_from_rows(rows))

@app.route("/api/admin/gold-rates/override", methods=["PATCH"])
@require_auth
@require_super_admin
def admin_gold_rates_override():
    data = request.get_json(silent=True) or {}
    is_manual = "1" if data.get("is_manual") in [True, "1", 1] else "0"
    m22k = str(data.get("manual_22k", ""))
    m24k = str(data.get("manual_24k", ""))

    db = get_db()
    for key, val in [("gold_is_manual", is_manual), ("gold_manual_22k", m22k), ("gold_manual_24k", m24k)]:
        if val != "":
            db.execute("""
                INSERT INTO site_settings (setting_key, setting_value, updated_by)
                VALUES (?, ?, ?)
                ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value, updated_by=excluded.updated_by, updated_at=CURRENT_TIMESTAMP
            """, (key, val, g.current_admin["id"]))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "UPDATE_GOLD_RATE_SETTINGS", "Gold Rates")
    return jsonify({"success": True})

# ══════════════════════════════════════════════════════════════════
# USERS CRUD
# ══════════════════════════════════════════════════════════════════
@app.route("/api/admin/users", methods=["GET"])
@require_auth
def admin_get_users():
    page = max(1, int(request.args.get("page", 1)))
    limit = min(100, int(request.args.get("limit", 20)))
    offset = (page - 1) * limit
    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip()

    where = ["1=1"]
    params = []
    if search:
        where.append("(name LIKE ? OR email LIKE ? OR phone LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    if status in ["ACTIVE", "DISABLED"]:
        where.append("u.status = ?")
        params.append(status)

    where_str = " AND ".join(where)
    db = get_db()
    total = db.execute(f"SELECT COUNT(*) FROM users u WHERE {where_str}", params).fetchone()[0]

    rows = db.execute(f"""
        SELECT u.*,
               COUNT(o.id) as order_count,
               COALESCE(SUM(o.total_amount), 0) as total_spent
        FROM users u
        LEFT JOIN orders o ON o.user_id = u.id
        WHERE {where_str}
        GROUP BY u.id
        ORDER BY u.created_at DESC
        LIMIT ? OFFSET ?
    """, list(params) + [limit, offset]).fetchall()

    return jsonify({
        "users": list_from_rows(rows),
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if limit > 0 else 1
    })

@app.route("/api/admin/users/<int:id>", methods=["GET"])
@require_auth
def admin_get_user(id):
    db = get_db()
    user = db.execute("""
        SELECT u.*, COUNT(o.id) as order_count, COALESCE(SUM(o.total_amount), 0) as total_spent
        FROM users u LEFT JOIN orders o ON o.user_id = u.id
        WHERE u.id = ? GROUP BY u.id
    """, (id,)).fetchone()
    if not user:
        return jsonify({"error": "User not found"}), 404

    orders = list_from_rows(db.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 20", (id,)).fetchall())
    return jsonify({"user": dict(user), "orders": orders})

@app.route("/api/admin/users/<int:id>", methods=["PATCH"])
@require_auth
def admin_update_user(id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in ["ACTIVE", "DISABLED"]:
        return jsonify({"error": "Invalid status"}), 400
    db = get_db()
    db.execute("UPDATE users SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, id))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], f"{status}_USER", "Users")
    return jsonify({"success": True})

@app.route("/api/admin/users/<int:id>", methods=["DELETE"])
@require_auth
def admin_delete_user(id):
    db = get_db()
    cnt = db.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND order_status NOT IN ('Delivered','Cancelled')", (id,)).fetchone()[0]
    if cnt > 0:
        return jsonify({"error": "Cannot delete user with active orders"}), 400
    db.execute("DELETE FROM users WHERE id = ?", (id,))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "DELETE_USER", "Users")
    return jsonify({"success": True})

# ══════════════════════════════════════════════════════════════════
# ADMIN ACCOUNTS MANAGEMENT (SUPER ADMIN ONLY)
# ══════════════════════════════════════════════════════════════════
@app.route("/api/admin/admins", methods=["GET"])
@require_auth
@require_super_admin
def admin_get_admins():
    db = get_db()
    rows = db.execute("SELECT id, name, email, role, status, last_login, created_at, updated_at FROM admins ORDER BY created_at ASC").fetchall()
    return jsonify(list_from_rows(rows))

@app.route("/api/admin/admins/<int:id>", methods=["GET"])
@require_auth
@require_super_admin
def admin_get_admin_detail(id):
    db = get_db()
    admin = db.execute("SELECT id, name, email, role, status, last_login, created_at, updated_at FROM admins WHERE id = ?", (id,)).fetchone()
    if not admin:
        return jsonify({"error": "Admin not found"}), 404
    return jsonify(dict(admin))

@app.route("/api/admin/admins", methods=["POST"])
@require_auth
@require_super_admin
def admin_create_admin():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    confirm_password = data.get("confirm_password") or ""
    role = data.get("role", "ADMIN")
    status = data.get("status", "ACTIVE")

    if not name or not email or not password:
        return jsonify({"error": "All fields are required"}), 400
    if password != confirm_password:
        return jsonify({"error": "Passwords do not match"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if role not in ["ADMIN", "SUPER_ADMIN"]:
        return jsonify({"error": "Invalid role"}), 400

    db = get_db()
    exists = db.execute("SELECT id FROM admins WHERE email = ?", (email,)).fetchone()
    if exists:
        return jsonify({"error": "An admin with this email already exists"}), 400

    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")
    cursor = db.execute(
        "INSERT INTO admins (name, email, password_hash, role, status) VALUES (?, ?, ?, ?, ?)",
        (name, email, pw_hash, role, status)
    )
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "CREATE_ADMIN", "Admin Accounts", notes=f"Created {role} {email}")
    created = dict(db.execute("SELECT id, name, email, role, status, created_at FROM admins WHERE id = ?", (cursor.lastrowid,)).fetchone())
    return jsonify(created), 201

@app.route("/api/admin/admins/<int:id>", methods=["PUT"])
@require_auth
@require_super_admin
def admin_update_admin(id):
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    role = data.get("role", "ADMIN")
    status = data.get("status", "ACTIVE")

    if not name or not email:
        return jsonify({"error": "Name and email are required"}), 400

    db = get_db()
    check = db.execute("SELECT * FROM admins WHERE id = ?", (id,)).fetchone()
    if not check:
        return jsonify({"error": "Admin not found"}), 404

    # Prevent removing last active super admin
    if (role == "ADMIN" or status == "DISABLED") and check["role"] == "SUPER_ADMIN":
        cnt = db.execute("SELECT COUNT(*) FROM admins WHERE role = 'SUPER_ADMIN' AND status = 'ACTIVE'").fetchone()[0]
        if cnt <= 1:
            return jsonify({"error": "At least one active Super Admin account is required."}), 400

    db.execute("UPDATE admins SET name=?, email=?, role=?, status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (name, email, role, status, id))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "UPDATE_ADMIN", "Admin Accounts", notes=f"Updated {email}")
    updated = dict(db.execute("SELECT id, name, email, role, status, last_login, created_at, updated_at FROM admins WHERE id = ?", (id,)).fetchone())
    return jsonify(updated)

@app.route("/api/admin/admins/<int:id>/status", methods=["PATCH"])
@require_auth
@require_super_admin
def admin_update_admin_status(id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in ["ACTIVE", "DISABLED"]:
        return jsonify({"error": "Invalid status"}), 400

    db = get_db()
    check = db.execute("SELECT * FROM admins WHERE id = ?", (id,)).fetchone()
    if not check:
        return jsonify({"error": "Admin not found"}), 404

    if status == "DISABLED" and check["role"] == "SUPER_ADMIN":
        cnt = db.execute("SELECT COUNT(*) FROM admins WHERE role = 'SUPER_ADMIN' AND status = 'ACTIVE'").fetchone()[0]
        if cnt <= 1:
            return jsonify({"error": "At least one active Super Admin account is required."}), 400

    db.execute("UPDATE admins SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, id))
    db.commit()
    action = "ENABLE_ADMIN" if status == "ACTIVE" else "DISABLE_ADMIN"
    log_action(g.current_admin["id"], g.current_admin["email"], action, "Admin Accounts")
    return jsonify({"success": True})

@app.route("/api/admin/admins/<int:id>/reset-password", methods=["POST"])
@require_auth
@require_super_admin
def admin_reset_password(id):
    data = request.get_json(silent=True) or {}
    new_pw = data.get("new_password") or ""
    confirm_pw = data.get("confirm_password") or ""

    if not new_pw or len(new_pw) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if new_pw != confirm_pw:
        return jsonify({"error": "Passwords do not match"}), 400

    db = get_db()
    pw_hash = bcrypt.hashpw(new_pw.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")
    db.execute("UPDATE admins SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (pw_hash, id))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "RESET_ADMIN_PASSWORD", "Admin Accounts")
    return jsonify({"success": True})

# ══════════════════════════════════════════════════════════════════
# SITE SETTINGS CRUD
# ══════════════════════════════════════════════════════════════════
@app.route("/api/admin/settings", methods=["GET"])
@require_auth
def admin_get_settings():
    db = get_db()
    rows = db.execute("SELECT setting_key, setting_value FROM site_settings").fetchall()
    return jsonify({r["setting_key"]: r["setting_value"] for r in rows})

@app.route("/api/admin/settings", methods=["PUT"])
@require_auth
@require_super_admin
def admin_update_settings():
    data = request.get_json(silent=True) or {}
    db = get_db()
    for key, val in data.items():
        db.execute("""
            INSERT INTO site_settings (setting_key, setting_value, updated_by)
            VALUES (?, ?, ?)
            ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value, updated_by=excluded.updated_by, updated_at=CURRENT_TIMESTAMP
        """, (key, str(val), g.current_admin["id"]))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "UPDATE_SETTINGS", "Site Settings")
    return jsonify({"success": True})

# ══════════════════════════════════════════════════════════════════
# ACCESS LOGS
# ══════════════════════════════════════════════════════════════════
@app.route("/api/admin/logs", methods=["GET"])
@require_auth
@require_super_admin
def admin_get_logs():
    page = max(1, int(request.args.get("page", 1)))
    limit = min(100, int(request.args.get("limit", 50)))
    offset = (page - 1) * limit
    search = request.args.get("search", "").strip()
    action = request.args.get("action", "").strip()
    module = request.args.get("module", "").strip()
    status = request.args.get("status", "").strip()
    date_from = request.args.get("dateFrom", "").strip()
    date_to = request.args.get("dateTo", "").strip()
    sort_dir = "ASC" if request.args.get("sort") == "asc" else "DESC"

    where = ["1=1"]
    params = []
    if search:
        where.append("(l.admin_email LIKE ? OR l.action LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if action:
        where.append("l.action = ?")
        params.append(action)
    if module:
        where.append("l.module = ?")
        params.append(module)
    if status in ["SUCCESS", "FAILURE"]:
        where.append("l.status = ?")
        params.append(status)
    if date_from:
        where.append("DATE(l.created_at) >= ?")
        params.append(date_from)
    if date_to:
        where.append("DATE(l.created_at) <= ?")
        params.append(date_to)

    where_str = " AND ".join(where)
    db = get_db()
    total = db.execute(f"SELECT COUNT(*) FROM admin_access_logs l WHERE {where_str}", params).fetchone()[0]
    rows = db.execute(f"""
        SELECT l.*, a.name as admin_name
        FROM admin_access_logs l
        LEFT JOIN admins a ON a.id = l.admin_id
        WHERE {where_str}
        ORDER BY l.created_at {sort_dir}
        LIMIT ? OFFSET ?
    """, list(params) + [limit, offset]).fetchall()

    return jsonify({
        "logs": list_from_rows(rows),
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if limit > 0 else 1
    })

@app.route("/api/admin/logs/actions", methods=["GET"])
@require_auth
@require_super_admin
def admin_get_log_actions():
    db = get_db()
    rows = db.execute("SELECT DISTINCT action FROM admin_access_logs ORDER BY action").fetchall()
    return jsonify([r["action"] for r in rows])

# ══════════════════════════════════════════════════════════════════
# STATIC FILE SERVING
# ══════════════════════════════════════════════════════════════════
@app.route("/")
def serve_index():
    return send_from_directory(str(BASE_DIR), "index.html")

@app.route("/<path:filename>")
def serve_static(filename):
    file_path = BASE_DIR / filename
    if file_path.is_file():
        return send_from_directory(str(BASE_DIR), filename)
    return send_from_directory(str(BASE_DIR), "index.html")

# ── Server Runner ──
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    print(f"\n[OK] THE 22KT GOLD Python Server running at http://localhost:{port}")
    print(f"[API] Admin Dashboard: http://localhost:{port}/admin-login.html")
    print(f"[API] Gold Rate API:   http://localhost:{port}/api/gold-rates")
    print(f"[DB]  Database:        {DB_PATH}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
