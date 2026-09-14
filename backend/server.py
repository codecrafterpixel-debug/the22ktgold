#!/usr/bin/env python3
"""
backend/server.py — THE 22KT GOLD | Python Flask & SQLite/PostgreSQL Dynamic Backend Server
Provides full API endpoints for Storefront Public APIs, Admin Dashboard,
Gold Rates, Authentication, Order Management, Customer Management, and Static Web Hosting.
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

try:
    import psycopg2
    from psycopg2.extras import DictCursor
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False
    DictCursor = object

# ── Paths & Environment Setup ──
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "the22ktgold.db"

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
PGHOST = os.environ.get("PGHOST", "127.0.0.1")
PGPORT = int(os.environ.get("PGPORT", "5432"))
PGDATABASE = os.environ.get("PGDATABASE", "the22ktgold")
PGUSER = os.environ.get("PGUSER", "postgres")
PGPASSWORD = os.environ.get("PGPASSWORD", "")
PGSSLMODE = os.environ.get("PGSSLMODE", "prefer")

UPLOADS_DIR = BASE_DIR / "uploads"
IMAGES_DIR = BASE_DIR / "images"
try:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
except Exception as e:
    print(f"Error creating directories: {e}", file=sys.stderr)

app = Flask(__name__, static_folder=str(BASE_DIR))
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

JWT_SECRET = os.environ.get("JWT_SECRET", "").strip() or "the22ktgold_secure_jwt_secret_key_2026"
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_HOURS = 24

# ── Database Layer (Dual SQLite / PostgreSQL Support) ──

def is_postgres_available():
    if not HAS_PSYCOPG2:
        return False
    if not DATABASE_URL and not os.environ.get("PGHOST"):
        return False
    try:
        kwargs = {"connect_timeout": 2}
        if DATABASE_URL:
            kwargs["dsn"] = DATABASE_URL
        else:
            kwargs.update({
                "host": PGHOST, "port": PGPORT, "dbname": PGDATABASE,
                "user": PGUSER, "password": PGPASSWORD, "sslmode": PGSSLMODE
            })
        conn = psycopg2.connect(**kwargs)
        conn.close()
        return True
    except Exception:
        return False

USE_POSTGRES = is_postgres_available()


class UniversalCursor:
    """Wrapper that provides dict-like rows and lastrowid across SQLite and PostgreSQL."""
    def __init__(self, raw_cursor, is_pg=False):
        self.raw = raw_cursor
        self.is_pg = is_pg
        self._lastrowid = getattr(raw_cursor, "lastrowid", None)

    @property
    def lastrowid(self):
        return self._lastrowid

    def _convert_row(self, row):
        if row is None:
            return None
        if hasattr(row, "keys"):
            return dict(row)
        if isinstance(row, tuple) and self.raw.description:
            cols = [d[0] for d in self.raw.description]
            return dict(zip(cols, row))
        return row

    def fetchone(self):
        row = self.raw.fetchone()
        return self._convert_row(row)

    def fetchall(self):
        rows = self.raw.fetchall()
        return [self._convert_row(r) for r in rows]

    def execute(self, sql, params=None):
        params = tuple(params) if params is not None else ()
        if self.is_pg:
            pg_sql = sql.replace("?", "%s")
            normalized = pg_sql.lstrip().upper()
            if normalized.startswith("INSERT") and "RETURNING" not in normalized:
                pg_sql = pg_sql.rstrip().rstrip(";") + " RETURNING id"
                self.raw.execute(pg_sql, params)
                row = self.raw.fetchone()
                if row:
                    self._lastrowid = row[0] if isinstance(row, tuple) else row.get("id")
                return self
            self.raw.execute(pg_sql, params)
            return self
        else:
            # SQLite
            self.raw.execute(sql, params)
            self._lastrowid = self.raw.lastrowid
            return self

    def executemany(self, sql, seq_of_params):
        if self.is_pg:
            pg_sql = sql.replace("?", "%s")
            self.raw.executemany(pg_sql, seq_of_params)
        else:
            self.raw.executemany(sql, seq_of_params)
        return self


class DBConnection:
    def __init__(self):
        self.is_pg = USE_POSTGRES
        if self.is_pg:
            kwargs = {"connect_timeout": 10, "cursor_factory": DictCursor}
            if DATABASE_URL:
                kwargs["dsn"] = DATABASE_URL
            else:
                kwargs.update({
                    "host": PGHOST, "port": PGPORT, "dbname": PGDATABASE,
                    "user": PGUSER, "password": PGPASSWORD, "sslmode": PGSSLMODE
                })
            self._conn = psycopg2.connect(**kwargs)
        else:
            self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row

    def cursor(self):
        return UniversalCursor(self._conn.cursor(), is_pg=self.is_pg)

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        try:
            self._conn.rollback()
        except Exception:
            pass

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


def get_db():
    if "db" not in g:
        g.db = DBConnection()
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        try:
            if error:
                db.rollback()
        finally:
            db.close()


def init_db():
    """Initializes schema and seeds starter records if needed."""
    conn = DBConnection()
    try:
        cur = conn.cursor()
        
        # 1. Admins
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(120) NOT NULL,
                email VARCHAR(200) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'ADMIN',
                status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
                last_login TIMESTAMP NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """ if not conn.is_pg else """
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                email VARCHAR(200) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'ADMIN' CHECK (role IN ('ADMIN','SUPER_ADMIN')),
                status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','DISABLED')),
                last_login TIMESTAMP NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. Admin Access Logs
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_access_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NULL,
                admin_email VARCHAR(200) NULL,
                action VARCHAR(80) NOT NULL,
                module VARCHAR(60) NOT NULL,
                ip_address VARCHAR(60) NULL,
                user_agent TEXT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'SUCCESS',
                notes TEXT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """ if not conn.is_pg else """
            CREATE TABLE IF NOT EXISTS admin_access_logs (
                id SERIAL PRIMARY KEY,
                admin_id INTEGER NULL REFERENCES admins(id) ON DELETE SET NULL,
                admin_email VARCHAR(200) NULL,
                action VARCHAR(80) NOT NULL,
                module VARCHAR(60) NOT NULL,
                ip_address VARCHAR(60) NULL,
                user_agent TEXT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'SUCCESS',
                notes TEXT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 3. Site Settings
        cur.execute("""
            CREATE TABLE IF NOT EXISTS site_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                setting_key VARCHAR(100) NOT NULL UNIQUE,
                setting_value TEXT NULL,
                updated_by INTEGER NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """ if not conn.is_pg else """
            CREATE TABLE IF NOT EXISTS site_settings (
                id SERIAL PRIMARY KEY,
                setting_key VARCHAR(100) NOT NULL UNIQUE,
                setting_value TEXT NULL,
                updated_by INTEGER NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 4. Users (Customers)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(200) NOT NULL,
                email VARCHAR(200) NOT NULL UNIQUE,
                phone VARCHAR(20) NULL,
                city VARCHAR(100) NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """ if not conn.is_pg else """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                email VARCHAR(200) NOT NULL UNIQUE,
                phone VARCHAR(20) NULL,
                city VARCHAR(100) NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 5. Categories
        cur.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(120) NOT NULL,
                slug VARCHAR(140) NOT NULL UNIQUE,
                description TEXT NULL,
                image VARCHAR(255) NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """ if not conn.is_pg else """
            CREATE TABLE IF NOT EXISTS categories (
                id SERIAL PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                slug VARCHAR(140) NOT NULL UNIQUE,
                description TEXT NULL,
                image VARCHAR(255) NULL,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 6. Products
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(200) NOT NULL,
                slug VARCHAR(220) NOT NULL UNIQUE,
                category_id INTEGER NULL,
                description TEXT NULL,
                purity INTEGER NOT NULL DEFAULT 22,
                weight REAL NOT NULL DEFAULT 0,
                making_charges REAL NOT NULL DEFAULT 0,
                base_price REAL NOT NULL DEFAULT 0,
                current_price REAL NOT NULL DEFAULT 0,
                stock INTEGER NOT NULL DEFAULT 0,
                sku VARCHAR(80) NULL UNIQUE,
                featured INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """ if not conn.is_pg else """
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                slug VARCHAR(220) NOT NULL UNIQUE,
                category_id INTEGER NULL REFERENCES categories(id) ON DELETE SET NULL,
                description TEXT NULL,
                purity SMALLINT NOT NULL DEFAULT 22,
                weight DECIMAL(8,3) NOT NULL DEFAULT 0,
                making_charges DECIMAL(10,2) NOT NULL DEFAULT 0,
                base_price DECIMAL(12,2) NOT NULL DEFAULT 0,
                current_price DECIMAL(12,2) NOT NULL DEFAULT 0,
                stock INTEGER NOT NULL DEFAULT 0,
                sku VARCHAR(80) NULL UNIQUE,
                featured BOOLEAN NOT NULL DEFAULT FALSE,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 7. Product Images
        cur.execute("""
            CREATE TABLE IF NOT EXISTS product_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                image_url TEXT NOT NULL,
                is_primary INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """ if not conn.is_pg else """
            CREATE TABLE IF NOT EXISTS product_images (
                id SERIAL PRIMARY KEY,
                product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                image_url TEXT NOT NULL,
                is_primary BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 8. Orders
        cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number VARCHAR(40) NOT NULL UNIQUE,
                user_id INTEGER NULL,
                customer_name VARCHAR(200) NOT NULL,
                customer_phone VARCHAR(20) NULL,
                customer_email VARCHAR(200) NULL,
                address TEXT NULL,
                product_id INTEGER NULL,
                product_name VARCHAR(200) NOT NULL,
                product_image TEXT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                weight REAL NOT NULL DEFAULT 0,
                purity INTEGER NOT NULL DEFAULT 22,
                gold_rate_used REAL NOT NULL DEFAULT 0,
                making_charges REAL NOT NULL DEFAULT 0,
                gst REAL NOT NULL DEFAULT 0,
                total_amount REAL NOT NULL DEFAULT 0,
                payment_method VARCHAR(50) NOT NULL DEFAULT 'Online',
                payment_status VARCHAR(30) NOT NULL DEFAULT 'Pending',
                order_status VARCHAR(30) NOT NULL DEFAULT 'Processing',
                notes TEXT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """ if not conn.is_pg else """
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                order_number VARCHAR(40) NOT NULL UNIQUE,
                user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
                customer_name VARCHAR(200) NOT NULL,
                customer_phone VARCHAR(20) NULL,
                customer_email VARCHAR(200) NULL,
                address TEXT NULL,
                product_id INTEGER NULL REFERENCES products(id) ON DELETE SET NULL,
                product_name VARCHAR(200) NOT NULL,
                product_image TEXT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                weight DECIMAL(8,3) NOT NULL DEFAULT 0,
                purity SMALLINT NOT NULL DEFAULT 22,
                gold_rate_used DECIMAL(10,2) NOT NULL DEFAULT 0,
                making_charges DECIMAL(10,2) NOT NULL DEFAULT 0,
                gst DECIMAL(10,2) NOT NULL DEFAULT 0,
                total_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
                payment_method VARCHAR(50) NOT NULL DEFAULT 'Online',
                payment_status VARCHAR(30) NOT NULL DEFAULT 'Pending',
                order_status VARCHAR(30) NOT NULL DEFAULT 'Processing',
                notes TEXT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 9. Gold Rates & History
        cur.execute("""
            CREATE TABLE IF NOT EXISTS gold_rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rate_24k REAL NOT NULL,
                rate_22k REAL NOT NULL,
                rate_18k REAL NOT NULL,
                change_24k REAL NOT NULL DEFAULT 0,
                change_22k REAL NOT NULL DEFAULT 0,
                change_18k REAL NOT NULL DEFAULT 0,
                change_percent REAL NOT NULL DEFAULT 0,
                provider VARCHAR(100) NOT NULL DEFAULT 'Spot Bullion Feed',
                is_manual INTEGER NOT NULL DEFAULT 0,
                fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """ if not conn.is_pg else """
            CREATE TABLE IF NOT EXISTS gold_rates (
                id SERIAL PRIMARY KEY,
                rate_24k DECIMAL(10,2) NOT NULL,
                rate_22k DECIMAL(10,2) NOT NULL,
                rate_18k DECIMAL(10,2) NOT NULL,
                change_24k DECIMAL(10,2) NOT NULL DEFAULT 0,
                change_22k DECIMAL(10,2) NOT NULL DEFAULT 0,
                change_18k DECIMAL(10,2) NOT NULL DEFAULT 0,
                change_percent DECIMAL(6,3) NOT NULL DEFAULT 0,
                provider VARCHAR(100) NOT NULL DEFAULT 'Spot Bullion Feed',
                is_manual BOOLEAN NOT NULL DEFAULT FALSE,
                fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS gold_rate_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rate_24k REAL NOT NULL,
                rate_22k REAL NOT NULL,
                rate_18k REAL NOT NULL,
                change_amount REAL NOT NULL DEFAULT 0,
                change_percent REAL NOT NULL DEFAULT 0,
                source VARCHAR(100) NOT NULL DEFAULT 'Bullion Feed',
                recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """ if not conn.is_pg else """
            CREATE TABLE IF NOT EXISTS gold_rate_history (
                id SERIAL PRIMARY KEY,
                rate_24k DECIMAL(10,2) NOT NULL,
                rate_22k DECIMAL(10,2) NOT NULL,
                rate_18k DECIMAL(10,2) NOT NULL,
                change_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
                change_percent DECIMAL(6,3) NOT NULL DEFAULT 0,
                source VARCHAR(100) NOT NULL DEFAULT 'Bullion Feed',
                recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 10. Enquiries
        cur.execute("""
            CREATE TABLE IF NOT EXISTS enquiries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(200) NOT NULL,
                phone VARCHAR(20) NULL,
                email VARCHAR(200) NULL,
                subject VARCHAR(200) NULL,
                message TEXT NOT NULL,
                status VARCHAR(30) NOT NULL DEFAULT 'New',
                admin_notes TEXT NULL,
                source VARCHAR(50) NOT NULL DEFAULT 'Website',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """ if not conn.is_pg else """
            CREATE TABLE IF NOT EXISTS enquiries (
                id SERIAL PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                phone VARCHAR(20) NULL,
                email VARCHAR(200) NULL,
                subject VARCHAR(200) NULL,
                message TEXT NOT NULL,
                status VARCHAR(30) NOT NULL DEFAULT 'New',
                admin_notes TEXT NULL,
                source VARCHAR(50) NOT NULL DEFAULT 'Website',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 11. Custom Orders
        cur.execute("""
            CREATE TABLE IF NOT EXISTS custom_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(200) NOT NULL,
                phone VARCHAR(20) NULL,
                email VARCHAR(200) NULL,
                address TEXT NULL,
                jewellery_type VARCHAR(100) NOT NULL,
                occasion VARCHAR(100) NULL,
                purity INTEGER NOT NULL DEFAULT 22,
                weight REAL NULL,
                size VARCHAR(50) NULL,
                finish VARCHAR(50) NULL,
                budget REAL NULL,
                description TEXT NULL,
                reference_link TEXT NULL,
                reference_image TEXT NULL,
                status VARCHAR(30) NOT NULL DEFAULT 'New',
                quote_amount REAL NULL,
                admin_notes TEXT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """ if not conn.is_pg else """
            CREATE TABLE IF NOT EXISTS custom_orders (
                id SERIAL PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                phone VARCHAR(20) NULL,
                email VARCHAR(200) NULL,
                address TEXT NULL,
                jewellery_type VARCHAR(100) NOT NULL,
                occasion VARCHAR(100) NULL,
                purity SMALLINT NOT NULL DEFAULT 22,
                weight DECIMAL(8,3) NULL,
                size VARCHAR(50) NULL,
                finish VARCHAR(50) NULL,
                budget DECIMAL(12,2) NULL,
                description TEXT NULL,
                reference_link TEXT NULL,
                reference_image TEXT NULL,
                status VARCHAR(30) NOT NULL DEFAULT 'New',
                quote_amount DECIMAL(12,2) NULL,
                admin_notes TEXT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 12. Gallery
        cur.execute("""
            CREATE TABLE IF NOT EXISTS gallery (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title VARCHAR(200) NOT NULL,
                image_url TEXT NOT NULL,
                alt_text VARCHAR(255) NULL,
                category VARCHAR(80) NULL,
                featured INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """ if not conn.is_pg else """
            CREATE TABLE IF NOT EXISTS gallery (
                id SERIAL PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                image_url TEXT NOT NULL,
                alt_text VARCHAR(255) NULL,
                category VARCHAR(80) NULL,
                featured BOOLEAN NOT NULL DEFAULT FALSE,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── Seeds ──
        # Admins
        cur.execute("SELECT COUNT(*) as cnt FROM admins")
        if cur.fetchone()["cnt"] == 0:
            pw_yash = bcrypt.hashpw("Yash2112".encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")
            pw_veer = bcrypt.hashpw("Veer@2112".encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")
            cur.execute(
                "INSERT INTO admins (name, email, password_hash, role, status) VALUES (?, ?, ?, ?, ?)",
                ("Yash Panchal", "22ktgold@yashpanchal.com", pw_yash, "SUPER_ADMIN", "ACTIVE")
            )
            cur.execute(
                "INSERT INTO admins (name, email, password_hash, role, status) VALUES (?, ?, ?, ?, ?)",
                ("Veer Shah", "22ktgold@veershah.com", pw_veer, "ADMIN", "ACTIVE")
            )

        # Categories
        cur.execute("SELECT COUNT(*) as cnt FROM categories")
        if cur.fetchone()["cnt"] == 0:
            cats = [
                ('Rings', 'rings', 'Handcrafted 22KT gold rings for every occasion.', 'images/cat-rings.jpg', 1),
                ('Necklaces', 'necklaces', 'Elegant gold necklaces and chains.', 'images/cat-necklaces.jpg', 1),
                ('Bangles', 'bangles', 'Timeless gold bangles and kadas.', 'images/cat-bangles.jpg', 1),
                ('Earrings', 'earrings', 'Delicate and statement gold earrings.', 'images/cat-earrings.jpg', 1),
                ('Bridal Sets', 'bridal-sets', 'Complete bridal jewellery collections.', 'images/cat-bridal.jpg', 1),
                ("Men's Gold", 'mens-gold', 'Masculine gold chains, bracelets and accessories.', 'images/cat-mens.jpg', 1)
            ]
            cur.executemany("INSERT INTO categories (name, slug, description, image, active) VALUES (?, ?, ?, ?, ?)", cats)

        # Products
        cur.execute("SELECT COUNT(*) as cnt FROM products")
        if cur.fetchone()["cnt"] == 0:
            prods = [
                ('Heritage Gold Ring', 'heritage-gold-ring', 1, 'Intricately hand-crafted 22KT gold ring with fine filigree detailing.', 22, 4.200, 500, 31000, 33500, 10, 'SKU-001', 1, 1),
                ('Royal Bridal Necklace', 'royal-bridal-necklace', 5, 'Traditional bridal masterpiece handcrafted for your grand wedding.', 22, 48.500, 5000, 350000, 375000, 3, 'SKU-002', 1, 1),
                ('Temple Gold Bangles', 'temple-gold-bangles', 3, 'Timeless antique finished 22KT bangles and kadas crafted to perfection.', 22, 32.000, 3000, 235000, 250000, 5, 'SKU-003', 1, 1),
                ("Classic Men's Chain", 'classic-mens-chain', 6, 'Durable and elegant 22KT machine-cut & hand-linked gold chain.', 22, 18.300, 2000, 135000, 142000, 8, 'SKU-004', 0, 1)
            ]
            for p in prods:
                cur.execute("""
                    INSERT INTO products (name, slug, category_id, description, purity, weight, making_charges, base_price, current_price, stock, sku, featured, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, p)
                pid = cur.lastrowid
                img_map = {1: 'images/cat-rings.jpg', 2: 'images/cat-necklaces.jpg', 3: 'images/cat-bangles.jpg', 4: 'images/cat-mens.jpg'}
                cur.execute("INSERT INTO product_images (product_id, image_url, is_primary) VALUES (?, ?, 1)", (pid, img_map.get(pid, 'images/cat-rings.jpg')))

        # Gallery
        cur.execute("SELECT COUNT(*) as cnt FROM gallery")
        if cur.fetchone()["cnt"] == 0:
            gall = [
                ('Royal Temple Bridal Necklace', 'images/hero-bg.jpg', 'Bridal Gold Jewellery', 'Bridal Sets', 1, 1),
                ('Hand-Carved Filigree Detailing', 'images/intro.jpg', 'Master Goldsmith at work', 'Workshop', 1, 1),
                ('Heritage Antique Gold Ring', 'images/product-1.jpg', '22KT Gold Ring', 'Rings', 1, 1),
                ('Artisan Bench & Polishing Unit', 'images/intro.jpg', 'In-House Manufacturing', 'Workshop', 0, 1),
                ('Antique Handcrafted Bangles', 'images/cat-bangles.jpg', '22KT Gold Bangles', 'Bangles', 1, 1),
                ('Traditional Royal Bridal Set', 'images/cat-bridal.jpg', 'Full bridal set', 'Bridal Sets', 1, 1)
            ]
            cur.executemany("INSERT INTO gallery (title, image_url, alt_text, category, featured, active) VALUES (?, ?, ?, ?, ?, ?)", gall)

        # Site Settings
        cur.execute("SELECT COUNT(*) as cnt FROM site_settings")
        if cur.fetchone()["cnt"] == 0:
            settings = [
                ('business_name', 'THE 22KT GOLD'),
                ('business_email', 'info@the22ktgold.in'),
                ('business_phone', '+91 94296 16414'),
                ('business_whatsapp', '+91 94296 16414'),
                ('business_address', 'Manek Chowk, Ahmedabad, Gujarat - 380001'),
                ('business_hours', 'Mon–Sat: 10:30 AM – 8:30 PM'),
                ('website_title', 'THE 22KT GOLD — Premium 22KT Gold Jewellery'),
                ('meta_description', 'Genuine 22KT gold jewellery direct from manufacturing in Manek Chowk, Ahmedabad.'),
                ('default_currency', 'INR'),
                ('default_country', 'India'),
                ('timezone', 'Asia/Kolkata'),
                ('contact_email', 'contact@the22ktgold.in'),
                ('support_phone', '+91 94296 16414'),
                ('instagram', 'https://instagram.com/the22ktgold'),
                ('facebook', 'https://facebook.com/the22ktgold'),
                ('footer_text', 'Crafted with love. Hallmarked for purity.'),
                ('copyright_text', '© 2026 THE 22KT GOLD. All rights reserved.'),
                ('gold_is_manual', '0'),
                ('gold_manual_22k', '7250'),
                ('gold_manual_24k', '7910')
            ]
            cur.executemany("INSERT INTO site_settings (setting_key, setting_value) VALUES (?, ?)", settings)

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"init_db error: {e}", file=sys.stderr)
    finally:
        conn.close()

# Auto-initialize database on import
try:
    init_db()
except Exception as e:
    print(f"init_db execution error: {e}", file=sys.stderr)


def make_slug(s):
    s = str(s).lower().strip()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'\s+', '-', s)
    return re.sub(r'-+', '-', s) or f"item-{int(time.time())}"

def safe_int(val, default=0):
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return int(val)
    cleaned = re.sub(r'[^\d-]', '', str(val))
    try:
        return int(cleaned) if cleaned and cleaned != '-' else default
    except (ValueError, TypeError):
        return default

def safe_float(val, default=0.0):
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    cleaned = re.sub(r'[^\d.-]', '', str(val))
    try:
        return float(cleaned) if cleaned and cleaned not in ('-', '.') else default
    except (ValueError, TypeError):
        return default

def dict_from_row(row):
    return dict(row) if row else None

def list_from_rows(rows):
    return [dict(r) for r in rows] if rows else []

def auto_register_or_find_user(db, name, email=None, phone=None, city=None):
    """Finds existing user by email or phone; creates a user if not found."""
    name = (name or "").strip()
    email = (email or "").strip().lower() if email else None
    phone = (phone or "").strip() if phone else None
    city = (city or "").strip() if city else None

    if not email and not phone:
        return None

    # Check existing
    user = None
    if email and phone:
        user = db.execute("SELECT id FROM users WHERE email = ? OR phone = ?", (email, phone)).fetchone()
    elif email:
        user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    elif phone:
        user = db.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()

    if user:
        return user["id"]

    # Insert new user
    dummy_email = email or f"user_{int(time.time())}_{phone[-4:] if len(phone)>=4 else '0000'}@customer.the22ktgold.in"
    cur = db.execute(
        "INSERT INTO users (name, email, phone, city, status) VALUES (?, ?, ?, ?, 'ACTIVE')",
        (name or "Valued Customer", dummy_email, phone, city)
    )
    db.commit()
    return cur.lastrowid


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
        
        # Standalone mock fallback token support
        if token.startswith("standalone_"):
            g.current_admin = {
                "id": 1,
                "email": request.headers.get("X-Admin-Email", "22ktgold@yashpanchal.com"),
                "name": "Admin",
                "role": "SUPER_ADMIN"
            }
            return f(*args, **kwargs)

        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            db = get_db()
            admin = db.execute("SELECT id, name, email, role, status FROM admins WHERE id = ?", (payload["id"],)).fetchone()
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


# ── Live Gold Rate Service ──
cached_gold_data = None
last_gold_fetch = 0
GOLD_CACHE_TTL = 60

def fetch_live_gold_rates():
    global cached_gold_data, last_gold_fetch
    now = time.time()
    
    # Check manual override in site settings
    try:
        db = get_db()
        rows = db.execute("SELECT setting_key, setting_value FROM site_settings WHERE setting_key IN ('gold_is_manual', 'gold_manual_22k', 'gold_manual_24k')").fetchall()
        settings = {r["setting_key"]: r["setting_value"] for r in rows}
        if settings.get("gold_is_manual") == "1" and settings.get("gold_manual_22k"):
            r22 = float(settings.get("gold_manual_22k", 7250))
            r24 = float(settings.get("gold_manual_24k", 7910))
            r18 = round(r24 * 0.75, 2)
            return {
                "rate24k": r24, "rate22k": r22, "rate18k": r18,
                "change24k": 0.0, "change22k": 0.0, "change18k": 0.0,
                "changePercent": 0.0, "provider": "Manual Admin Override",
                "isManual": True, "fetchedAt": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
    except Exception:
        pass

    if cached_gold_data and (now - last_gold_fetch) < GOLD_CACHE_TTL:
        return cached_gold_data

    api_key = os.environ.get("GOLD_API_KEY")
    rate_24k = 0
    change_24k = 0
    change_percent = 0
    provider = "Spot Bullion Feed"

    if api_key and api_key != "your_goldapi_io_token_here":
        try:
            r = requests.get("https://www.goldapi.io/api/XAU/INR", headers={"x-access-token": api_key, "Content-Type": "application/json"}, timeout=4)
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
            r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=pax-gold&vs_currencies=inr&include_24hr_change=true", timeout=4)
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
        rate_24k = 7910.0
        change_24k = 15.0
        change_percent = 0.21
        provider = "Ahmedabad Bullion Indicative"

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
        "isManual": False,
        "fetchedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "gold": {
            "22k": { "perGram": round(rate_22k, 2), "per10g": round(rate_22k * 10, 2), "change": round(change_22k, 2), "changePercent": round(change_percent, 2) },
            "24k": { "perGram": round(rate_24k, 2), "per10g": round(rate_24k * 10, 2), "change": round(change_24k, 2), "changePercent": round(change_percent, 2) },
            "18k": { "perGram": round(rate_18k, 2), "per10g": round(rate_18k * 10, 2), "change": round(change_18k, 2), "changePercent": round(change_percent, 2) }
        }
    }
    last_gold_fetch = now
    return cached_gold_data


# ══════════════════════════════════════════════════════════════════
# AUTH ROUTES (ADMIN & USERS)
# ══════════════════════════════════════════════════════════════════

@app.route("/api/admin/auth/login", methods=["POST"])
@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    # Normalize aliases
    if email in ["yashpanchal", "yash", "superadmin", "yashpanchal.com", "22ktgold@yashpanchal.com"]:
        email = "22ktgold@yashpanchal.com"
    elif email in ["veershah", "veer", "admin", "veershah.com", "22ktgold@veershah.com"]:
        email = "22ktgold@veershah.com"

    db = get_db()
    admin = db.execute("SELECT * FROM admins WHERE email = ?", (email,)).fetchone()
    if not admin:
        log_action(None, email, "LOGIN_FAILED", "Authentication", "FAILURE", "Email not found")
        return jsonify({"error": "Invalid email or password"}), 401

    if admin["status"] == "DISABLED":
        log_action(admin["id"], email, "LOGIN_BLOCKED", "Authentication", "FAILURE", "Disabled account")
        return jsonify({"error": "Your admin account has been disabled"}), 403

    pw_hash = admin["password_hash"]
    # Check bcrypt or fallback for dev
    valid = False
    try:
        valid = bcrypt.checkpw(password.encode("utf-8"), pw_hash.encode("utf-8"))
    except Exception:
        pass

    if not valid:
        # Check hardcoded developer admin passwords with alias support
        if (email == "22ktgold@yashpanchal.com" and password.lower() in ["yash2112", "yash@2112"]) or \
           (email == "22ktgold@veershah.com" and password.lower() in ["veer@2112", "veer2112"]):
            valid = True
            # Update password hash in db
            new_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")
            db.execute("UPDATE admins SET password_hash = ? WHERE id = ?", (new_hash, admin["id"]))
            db.commit()

    if not valid:
        log_action(admin["id"], email, "LOGIN_FAILED", "Authentication", "FAILURE", "Incorrect password")
        return jsonify({"error": "Invalid email or password"}), 401

    db.execute("UPDATE admins SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (admin["id"],))
    db.commit()

    token = sign_token(admin)
    log_action(admin["id"], email, "LOGIN_SUCCESS", "Authentication", "SUCCESS")

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
def admin_logout():
    return jsonify({"success": True, "message": "Logged out successfully"})


@app.route("/api/admin/auth/me", methods=["GET"])
@app.route("/api/admin/me", methods=["GET"])
@require_auth
def admin_me():
    return jsonify({"admin": g.current_admin})


# ══════════════════════════════════════════════════════════════════
# DASHBOARD OVERVIEW API
# ══════════════════════════════════════════════════════════════════

@app.route("/api/admin/dashboard", methods=["GET"])
@require_auth
def admin_dashboard():
    db = get_db()
    total_orders = db.execute("SELECT COUNT(*) as c FROM orders").fetchone()["c"]
    registered_users = db.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    custom_requests = db.execute("SELECT COUNT(*) as c FROM custom_orders").fetchone()["c"]
    open_enquiries = db.execute("SELECT COUNT(*) as c FROM enquiries WHERE status IN ('New', 'Contacted', 'In Progress')").fetchone()["c"]

    recent_orders = db.execute("""
        SELECT id, order_number, customer_name, product_name, weight, total_amount, payment_status, order_status, created_at
        FROM orders ORDER BY created_at DESC LIMIT 6
    """).fetchall()

    total_products = db.execute("SELECT COUNT(*) as c FROM products WHERE active = 1").fetchone()["c"]
    total_rev_row = db.execute("SELECT SUM(total_amount) as s FROM orders WHERE payment_status IN ('Confirmed', 'Paid', 'Delivered', 'Completed')").fetchone()
    total_revenue = float(total_rev_row["s"] or 0) if total_rev_row else 0.0
    gold_data = fetch_live_gold_rates()

    return jsonify({
        "stats": {
            "totalOrders": total_orders,
            "registeredUsers": registered_users,
            "customRequests": custom_requests,
            "openEnquiries": open_enquiries,
            "totalProducts": total_products,
            "totalRevenue": total_revenue
        },
        "total_orders": total_orders,
        "total_users": registered_users,
        "total_products": total_products,
        "total_revenue": total_revenue,
        "recentOrders": list_from_rows(recent_orders),
        "gold": gold_data
    })


# ══════════════════════════════════════════════════════════════════
# PRODUCTS CRUD & PUBLIC APIS
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
    total = db.execute(f"SELECT COUNT(*) as c FROM products p WHERE {where_str}", params).fetchone()["c"]

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
    description = data.get("description") or ""
    purity = safe_int(data.get("purity"), 22)
    weight = safe_float(data.get("weight"), 0.0)
    making_charges = safe_float(data.get("making_charges"), 0.0)
    base_price = safe_float(data.get("base_price"), 0.0)
    current_price = safe_float(data.get("current_price"), 0.0)
    stock = safe_int(data.get("stock"), 0)
    sku = data.get("sku") or f"SKU-{int(time.time())}"
    featured = 1 if str(data.get("featured")).lower() in ["true", "1"] else 0
    active = 0 if str(data.get("active")).lower() in ["false", "0"] else 1

    if not name:
        return jsonify({"error": "Product name is required"}), 400

    slug = make_slug(name)
    db = get_db()
    
    # Check unique slug
    exists = db.execute("SELECT id FROM products WHERE slug = ?", (slug,)).fetchone()
    if exists:
        slug = f"{slug}-{int(time.time())}"

    # Check unique sku
    if sku:
        sku_exists = db.execute("SELECT id FROM products WHERE sku = ?", (sku,)).fetchone()
        if sku_exists:
            sku = f"{sku}-{int(time.time())}"

    cursor = db.execute("""
        INSERT INTO products (name, slug, category_id, description, purity, weight, making_charges, base_price, current_price, stock, sku, featured, active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, slug, category_id, description, purity, weight, making_charges, base_price, current_price, stock, sku, featured, active))
    product_id = cursor.lastrowid

    # Handle image file upload or image_url
    image_file = request.files.get("image")
    if image_file and image_file.filename:
        ext = Path(image_file.filename).suffix.lower()
        b64_str = base64.b64encode(image_file.read()).decode("utf-8")
        mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else f"image/{ext.replace('.', '') or 'png'}"
        img_url = f"data:{mime};base64,{b64_str}"
        db.execute("INSERT INTO product_images (product_id, image_url, is_primary) VALUES (?, ?, 1)", (product_id, img_url))
    elif data.get("image_url"):
        db.execute("INSERT INTO product_images (product_id, image_url, is_primary) VALUES (?, ?, 1)", (product_id, data.get("image_url")))
    else:
        # Default placeholder
        db.execute("INSERT INTO product_images (product_id, image_url, is_primary) VALUES (?, ?, 1)", (product_id, "images/cat-rings.jpg"))

    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "CREATE_PRODUCT", "Products", notes=f"Created {name}")

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
    purity = safe_int(data.get("purity"), check["purity"])
    weight = safe_float(data.get("weight"), check["weight"])
    making_charges = safe_float(data.get("making_charges"), check["making_charges"])
    base_price = safe_float(data.get("base_price"), check["base_price"])
    current_price = safe_float(data.get("current_price"), check["current_price"])
    stock = safe_int(data.get("stock"), check["stock"])
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
        b64_str = base64.b64encode(image_file.read()).decode("utf-8")
        mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else f"image/{ext.replace('.', '') or 'png'}"
        img_url = f"data:{mime};base64,{b64_str}"
        db.execute("UPDATE product_images SET is_primary = 0 WHERE product_id = ?", (id,))
        db.execute("INSERT INTO product_images (product_id, image_url, is_primary) VALUES (?, ?, 1)", (id, img_url))
    elif data.get("image_url"):
        db.execute("UPDATE product_images SET is_primary = 0 WHERE product_id = ?", (id,))
        db.execute("INSERT INTO product_images (product_id, image_url, is_primary) VALUES (?, ?, 1)", (id, data.get("image_url")))

    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "UPDATE_PRODUCT", "Products", notes=f"Updated {name}")
    updated = dict(db.execute("SELECT * FROM products WHERE id = ?", (id,)).fetchone())
    return jsonify(updated)


@app.route("/api/admin/products/<int:id>", methods=["DELETE"])
@require_auth
def admin_delete_product(id):
    db = get_db()
    check = db.execute("SELECT id FROM products WHERE id = ?", (id,)).fetchone()
    if not check:
        return jsonify({"error": "Product not found"}), 404
    db.execute("UPDATE products SET active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (id,))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "DELETE_PRODUCT", "Products", notes=f"Deactivated product {id}")
    return jsonify({"success": True})


# ── Public Products Endpoints ──

@app.route("/api/products", methods=["GET", "POST", "DELETE"])
def public_products():
    db = get_db()
    if request.method == "GET":
        category_slug_or_id = request.args.get("category", "").strip()
        featured = request.args.get("featured")
        search = request.args.get("search", "").strip()

        where = ["p.active = 1"]
        params = []

        if category_slug_or_id:
            if category_slug_or_id.isdigit():
                where.append("p.category_id = ?")
                params.append(int(category_slug_or_id))
            else:
                where.append("(c.slug = ? OR c.name LIKE ?)")
                params.extend([category_slug_or_id.lower(), f"%{category_slug_or_id}%"])

        if featured in ["1", "true", True]:
            where.append("p.featured = 1")

        if search:
            where.append("(p.name LIKE ? OR p.description LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

        where_str = " AND ".join(where)

        rows = db.execute(f"""
            SELECT p.*, p.name as title, c.name as category_name, c.slug as category_slug,
                   COALESCE((SELECT image_url FROM product_images pi WHERE pi.product_id = p.id AND pi.is_primary = 1 LIMIT 1), 'images/cat-rings.jpg') as image
            FROM products p
            LEFT JOIN categories c ON c.id = p.category_id
            WHERE {where_str}
            ORDER BY p.featured DESC, p.created_at DESC
        """, params).fetchall()

        return jsonify(list_from_rows(rows))

    if request.method == "POST":
        data = request.get_json(silent=True) or request.form.to_dict() or {}
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
        return jsonify({"id": pid, "name": name, "title": name, "slug": slug}), 201

    if request.method == "DELETE":
        pid = request.args.get("id")
        if pid:
            db.execute("UPDATE products SET active = 0 WHERE id = ? OR sku = ?", (pid, pid))
            db.commit()
            return jsonify({"success": True})
        return jsonify({"error": "Missing id"}), 400


@app.route("/api/products/<int:id>", methods=["GET"])
def public_get_product(id):
    db = get_db()
    product = db.execute("""
        SELECT p.*, p.name as title, c.name as category_name, c.slug as category_slug
        FROM products p LEFT JOIN categories c ON c.id = p.category_id
        WHERE p.id = ? AND p.active = 1
    """, (id,)).fetchone()
    if not product:
        return jsonify({"error": "Product not found"}), 404

    images = list_from_rows(db.execute("SELECT * FROM product_images WHERE product_id = ? ORDER BY is_primary DESC", (id,)).fetchall())
    res = dict(product)
    res["images"] = images
    res["primary_image"] = images[0]["image_url"] if images else "images/cat-rings.jpg"
    res["image"] = res["primary_image"]
    return jsonify(res)


# ══════════════════════════════════════════════════════════════════
# CATEGORIES CRUD & PUBLIC APIS
# ══════════════════════════════════════════════════════════════════

@app.route("/api/categories", methods=["GET"])
@app.route("/api/admin/categories", methods=["GET"])
def get_categories():
    search = request.args.get("search", "").strip()
    db = get_db()
    where = ["1=1"]
    params = []
    if search:
        where.append("c.name LIKE ?")
        params.append(f"%{search}%")

    where_str = " AND ".join(where)
    rows = db.execute(f"""
        SELECT c.*, COUNT(p.id) as product_count
        FROM categories c
        LEFT JOIN products p ON p.category_id = c.id AND p.active = 1
        WHERE {where_str}
        GROUP BY c.id
        ORDER BY c.name ASC
    """, params).fetchall()

    return jsonify(list_from_rows(rows))


@app.route("/api/admin/categories", methods=["POST"])
@require_auth
def admin_create_category():
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    name = (data.get("name") or "").strip()
    description = data.get("description") or ""
    image = data.get("image") or ""
    active = 1 if str(data.get("active", True)).lower() in ["true", "1"] else 0

    if not name:
        return jsonify({"error": "Category name is required"}), 400

    slug = make_slug(name)
    db = get_db()
    exists = db.execute("SELECT id FROM categories WHERE slug = ?", (slug,)).fetchone()
    if exists:
        slug = f"{slug}-{int(time.time())}"

    cursor = db.execute(
        "INSERT INTO categories (name, slug, description, image, active) VALUES (?, ?, ?, ?, ?)",
        (name, slug, description, image, active)
    )
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "CREATE_CATEGORY", "Categories", notes=f"Created {name}")
    created = dict(db.execute("SELECT * FROM categories WHERE id = ?", (cursor.lastrowid,)).fetchone())
    return jsonify(created), 201


@app.route("/api/admin/categories/<int:id>", methods=["PUT"])
@require_auth
def admin_update_category(id):
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    db = get_db()
    check = db.execute("SELECT * FROM categories WHERE id = ?", (id,)).fetchone()
    if not check:
        return jsonify({"error": "Category not found"}), 404

    name = (data.get("name") or check["name"]).strip()
    slug = make_slug(name)
    description = data.get("description", check["description"])
    image = data.get("image", check["image"])
    active = 1 if str(data.get("active", check["active"])).lower() in ["true", "1"] else 0

    db.execute(
        "UPDATE categories SET name=?, slug=?, description=?, image=?, active=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (name, slug, description, image, active, id)
    )
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "UPDATE_CATEGORY", "Categories", notes=f"Updated {name}")
    updated = dict(db.execute("SELECT * FROM categories WHERE id = ?", (id,)).fetchone())
    return jsonify(updated)


@app.route("/api/admin/categories/<int:id>", methods=["DELETE"])
@require_auth
def admin_delete_category(id):
    db = get_db()
    check = db.execute("SELECT id FROM categories WHERE id = ?", (id,)).fetchone()
    if not check:
        return jsonify({"error": "Category not found"}), 404

    # Check products assigned
    count = db.execute("SELECT COUNT(*) as c FROM products WHERE category_id = ? AND active = 1", (id,)).fetchone()["c"]
    if count > 0:
        return jsonify({"error": f"Cannot delete category with {count} active products. Reassign them first."}), 400

    db.execute("DELETE FROM categories WHERE id = ?", (id,))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "DELETE_CATEGORY", "Categories", notes=f"Deleted category {id}")
    return jsonify({"success": True})


# ══════════════════════════════════════════════════════════════════
# GALLERY CRUD & PUBLIC APIS
# ══════════════════════════════════════════════════════════════════

@app.route("/api/gallery", methods=["GET"])
@app.route("/api/admin/gallery", methods=["GET"])
def get_gallery():
    category = request.args.get("category", "").strip()
    db = get_db()
    where = ["active = 1"]
    params = []
    if category and category.lower() != "all":
        where.append("(LOWER(category) = ? OR LOWER(category) LIKE ?)")
        params.extend([category.lower(), f"%{category.lower()}%"])

    where_str = " AND ".join(where)
    rows = db.execute(f"""
        SELECT * FROM gallery
        WHERE {where_str}
        ORDER BY featured DESC, created_at DESC
    """, params).fetchall()

    items = list_from_rows(rows)
    return jsonify({"items": items, "gallery": items, "total": len(items)})


@app.route("/api/admin/gallery", methods=["POST"])
@require_auth
def admin_create_gallery_item():
    data = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    title = (data.get("title") or "").strip()
    alt_text = data.get("alt_text") or title
    category = data.get("category") or "General"
    featured = 1 if str(data.get("featured")).lower() in ["true", "1"] else 0

    if not title:
        return jsonify({"error": "Title is required"}), 400

    img_url = data.get("image_url") or ""
    image_file = request.files.get("image")
    if image_file and image_file.filename:
        ext = Path(image_file.filename).suffix.lower()
        b64_str = base64.b64encode(image_file.read()).decode("utf-8")
        mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else f"image/{ext.replace('.', '') or 'png'}"
        img_url = f"data:{mime};base64,{b64_str}"

    if not img_url:
        return jsonify({"error": "Image is required"}), 400

    db = get_db()
    cur = db.execute(
        "INSERT INTO gallery (title, image_url, alt_text, category, featured, active) VALUES (?, ?, ?, ?, ?, 1)",
        (title, img_url, alt_text, category, featured)
    )
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "UPLOAD_GALLERY", "Gallery", notes=f"Uploaded {title}")
    created = dict(db.execute("SELECT * FROM gallery WHERE id = ?", (cur.lastrowid,)).fetchone())
    return jsonify(created), 201


@app.route("/api/admin/gallery/<int:id>", methods=["PATCH"])
@require_auth
def admin_update_gallery_item(id):
    data = request.get_json(silent=True) or {}
    db = get_db()
    updates = []
    params = []
    if "featured" in data:
        updates.append("featured = ?")
        params.append(1 if data["featured"] in [1, "1", True, "true"] else 0)
    if "category" in data:
        updates.append("category = ?")
        params.append(data["category"])
    if "title" in data:
        updates.append("title = ?")
        params.append(data["title"])

    if not updates:
        return jsonify({"error": "Nothing to update"}), 400

    params.append(id)
    db.execute(f"UPDATE gallery SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", params)
    db.commit()
    return jsonify({"success": True})


@app.route("/api/admin/gallery/<int:id>", methods=["DELETE"])
@require_auth
def admin_delete_gallery_item(id):
    db = get_db()
    db.execute("DELETE FROM gallery WHERE id = ?", (id,))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "DELETE_GALLERY", "Gallery", notes=f"Deleted gallery item {id}")
    return jsonify({"success": True})


# ══════════════════════════════════════════════════════════════════
# ORDERS CRUD & PUBLIC APIS
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

    where = ["1=1"]
    params = []
    if search:
        where.append("(order_number LIKE ? OR customer_name LIKE ? OR customer_email LIKE ? OR customer_phone LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])
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
    total = db.execute(f"SELECT COUNT(*) as c FROM orders WHERE {where_str}", params).fetchone()["c"]

    rows = db.execute(f"""
        SELECT * FROM orders WHERE {where_str} ORDER BY created_at DESC LIMIT ? OFFSET ?
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
    log_action(g.current_admin["id"], g.current_admin["email"], "UPDATE_ORDER", "Orders", notes=f"Updated order {id}")
    updated = dict(db.execute("SELECT * FROM orders WHERE id = ?", (id,)).fetchone())
    return jsonify(updated)


@app.route("/api/admin/orders/<int:id>", methods=["DELETE"])
@require_auth
def admin_cancel_order(id):
    db = get_db()
    db.execute("UPDATE orders SET order_status = 'Cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (id,))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "CANCEL_ORDER", "Orders", notes=f"Cancelled order {id}")
    return jsonify({"success": True})


@app.route("/api/orders", methods=["POST"])
@app.route("/api/admin/orders", methods=["POST"])
def create_order():
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    customer_name = (data.get("customer_name") or data.get("name") or "").strip()
    customer_phone = data.get("customer_phone") or data.get("phone")
    customer_email = data.get("customer_email") or data.get("email")
    address = data.get("address") or data.get("city")
    product_id = data.get("product_id")
    product_name = data.get("product_name") or "Custom 22KT Gold Jewellery"
    product_image = data.get("product_image") or data.get("image") or "images/cat-rings.jpg"
    quantity = safe_int(data.get("quantity"), 1)
    weight = safe_float(data.get("weight"), 0.0)
    purity = safe_int(data.get("purity"), 22)
    gold_rate_used = safe_float(data.get("gold_rate_used"), 0.0)
    making_charges = safe_float(data.get("making_charges"), 0.0)
    gst = safe_float(data.get("gst"), 0.0)
    total_amount = safe_float(data.get("total_amount") or data.get("price"), 0.0)
    payment_method = data.get("payment_method") or "Direct Workshop / WhatsApp"
    payment_status = data.get("payment_status") or "Pending"
    order_status = data.get("order_status") or "New"
    notes = data.get("notes") or ""

    if not customer_name:
        return jsonify({"error": "Customer name is required"}), 400

    db = get_db()
    user_id = auto_register_or_find_user(db, customer_name, customer_email, customer_phone, address)

    order_num = f"ORD-{datetime.date.today().strftime('%Y%m%d')}-{int(time.time()) % 10000:04d}"

    cursor = db.execute("""
        INSERT INTO orders (
            order_number, user_id, customer_name, customer_phone, customer_email, address,
            product_id, product_name, product_image, quantity, weight, purity,
            gold_rate_used, making_charges, gst, total_amount, payment_method, payment_status, order_status, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        order_num, user_id, customer_name, customer_phone, customer_email, address,
        product_id, product_name, product_image, quantity, weight, purity,
        gold_rate_used, making_charges, gst, total_amount, payment_method, payment_status, order_status, notes
    ))
    db.commit()

    return jsonify({
        "success": True,
        "order_number": order_num,
        "id": cursor.lastrowid,
        "order_id": cursor.lastrowid,
        "customer_name": customer_name,
        "product_name": product_name,
        "total_amount": total_amount
    }), 201


# ══════════════════════════════════════════════════════════════════
# CUSTOM ORDERS CRUD & PUBLIC APIS
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
        where.append("(name LIKE ? OR email LIKE ? OR phone LIKE ? OR jewellery_type LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])
    if status:
        where.append("status = ?")
        params.append(status)

    where_str = " AND ".join(where)
    db = get_db()
    total = db.execute(f"SELECT COUNT(*) as c FROM custom_orders WHERE {where_str}", params).fetchone()["c"]
    rows = db.execute(f"SELECT * FROM custom_orders WHERE {where_str} ORDER BY created_at DESC LIMIT ? OFFSET ?", list(params) + [limit, offset]).fetchall()

    return jsonify({
        "customOrders": list_from_rows(rows),
        "requests": list_from_rows(rows),
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
    if "quote_amount" in data and data["quote_amount"] != "":
        updates.append("quote_amount = ?")
        params.append(float(data["quote_amount"]))

    if not updates:
        return jsonify({"error": "Nothing to update"}), 400

    params.append(id)
    db.execute(f"UPDATE custom_orders SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", params)
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "UPDATE_CUSTOM_ORDER", "Custom Orders", notes=f"Updated custom order {id}")
    updated = dict(db.execute("SELECT * FROM custom_orders WHERE id = ?", (id,)).fetchone())
    return jsonify(updated)


@app.route("/api/admin/custom-orders/<int:id>", methods=["DELETE"])
@require_auth
def admin_reject_custom_order(id):
    db = get_db()
    db.execute("UPDATE custom_orders SET status = 'Rejected', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (id,))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "REJECT_CUSTOM_ORDER", "Custom Orders", notes=f"Rejected custom order {id}")
    return jsonify({"success": True})


@app.route("/api/custom-orders", methods=["POST"])
def public_create_custom_order():
    data = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    email = (data.get("email") or "").strip()
    address = data.get("address") or data.get("city")
    jewellery_type = data.get("jewellery_type") or data.get("type", "Custom 22KT Gold Piece")
    occasion = data.get("occasion")
    purity = int(re.sub(r'\D', '', str(data.get("purity") or "22")) or 22)
    weight = float(re.findall(r'[\d\.]+', str(data.get("weight") or 0))[0]) if re.findall(r'[\d\.]+', str(data.get("weight") or "")) else None
    size = data.get("size")
    finish = data.get("finish")
    budget = float(re.findall(r'[\d\.]+', str(data.get("budget") or 0))[0]) if re.findall(r'[\d\.]+', str(data.get("budget") or "")) else None
    description = data.get("description") or ""
    reference_link = data.get("reference_link")

    if not name:
        return jsonify({"error": "Name is required"}), 400

    ref_img = None
    image_file = request.files.get("reference_image") or request.files.get("image")
    if image_file and image_file.filename:
        ext = Path(image_file.filename).suffix.lower()
        b64_str = base64.b64encode(image_file.read()).decode("utf-8")
        mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else f"image/{ext.replace('.', '') or 'png'}"
        ref_img = f"data:{mime};base64,{b64_str}"
    elif data.get("reference_image"):
        ref_img = data.get("reference_image")

    db = get_db()
    user_id = auto_register_or_find_user(db, name, email, phone, address)

    cursor = db.execute("""
        INSERT INTO custom_orders (
            name, phone, email, address, jewellery_type, occasion, purity, weight,
            size, finish, budget, description, reference_link, reference_image, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'New')
    """, (name, phone, email, address, jewellery_type, occasion, purity, weight, size, finish, budget, description, reference_link, ref_img))
    db.commit()

    return jsonify({"success": True, "id": cursor.lastrowid, "user_id": user_id}), 201


# ══════════════════════════════════════════════════════════════════
# ENQUIRIES CRUD & PUBLIC APIS
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
        where.append("(name LIKE ? OR email LIKE ? OR phone LIKE ? OR message LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])
    if status:
        where.append("status = ?")
        params.append(status)

    where_str = " AND ".join(where)
    db = get_db()
    total = db.execute(f"SELECT COUNT(*) as c FROM enquiries WHERE {where_str}", params).fetchone()["c"]
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
    log_action(g.current_admin["id"], g.current_admin["email"], "UPDATE_ENQUIRY", "Enquiries", notes=f"Updated enquiry {id}")
    updated = dict(db.execute("SELECT * FROM enquiries WHERE id = ?", (id,)).fetchone())
    return jsonify(updated)


@app.route("/api/admin/enquiries/<int:id>", methods=["DELETE"])
@require_auth
def admin_delete_enquiry(id):
    db = get_db()
    db.execute("DELETE FROM enquiries WHERE id = ?", (id,))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "DELETE_ENQUIRY", "Enquiries", notes=f"Deleted enquiry {id}")
    return jsonify({"success": True})


@app.route("/api/enquiries", methods=["POST"])
def public_create_enquiry():
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    email = (data.get("email") or "").strip()
    city = data.get("city")
    subject = data.get("subject") or "General Website Enquiry"
    message = data.get("message") or ""
    source = data.get("source") or "Contact Page"

    if not name:
        return jsonify({"error": "Name is required"}), 400

    db = get_db()
    user_id = auto_register_or_find_user(db, name, email, phone, city)

    cursor = db.execute(
        "INSERT INTO enquiries (name, phone, email, subject, message, status, source) VALUES (?, ?, ?, ?, ?, 'New', ?)",
        (name, phone, email, subject, message, source)
    )
    db.commit()
    return jsonify({"success": True, "id": cursor.lastrowid, "user_id": user_id}), 201


# ══════════════════════════════════════════════════════════════════
# USERS (CUSTOMERS) CRUD & REGISTRATION
# ══════════════════════════════════════════════════════════════════

@app.route("/api/users", methods=["POST"])
@app.route("/api/auth/register", methods=["POST"])
def public_register_user():
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    name = (data.get("name") or "").strip()
    first = (data.get("first_name") or data.get("first") or "").strip()
    last = (data.get("last_name") or data.get("last") or "").strip()
    if not name and (first or last):
        name = f"{first} {last}".strip()

    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    city = data.get("city") or ""

    if not name or not email:
        return jsonify({"error": "Name and email are required"}), 400

    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        return jsonify({"success": True, "id": existing["id"], "message": "Welcome back!"})

    cur = db.execute(
        "INSERT INTO users (name, email, phone, city, status) VALUES (?, ?, ?, ?, 'ACTIVE')",
        (name, email, phone, city)
    )
    db.commit()
    return jsonify({"success": True, "id": cur.lastrowid, "name": name, "email": email}), 201


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
        where.append("(u.name LIKE ? OR u.email LIKE ? OR u.phone LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    if status in ["ACTIVE", "DISABLED"]:
        where.append("u.status = ?")
        params.append(status)

    where_str = " AND ".join(where)
    db = get_db()
    total = db.execute(f"SELECT COUNT(*) as c FROM users u WHERE {where_str}", params).fetchone()["c"]

    rows = db.execute(f"""
        SELECT u.*,
               COUNT(o.id) as order_count,
               COALESCE(SUM(o.total_amount), 0) as total_spent
        FROM users u
        LEFT JOIN orders o ON o.user_id = u.id OR o.customer_email = u.email
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
    user = db.execute("SELECT * FROM users WHERE id = ?", (id,)).fetchone()
    if not user:
        return jsonify({"error": "User not found"}), 404
    orders = db.execute("SELECT * FROM orders WHERE user_id = ? OR customer_email = ? ORDER BY created_at DESC", (id, user["email"])).fetchall()
    res = dict(user)
    res["orders"] = list_from_rows(orders)
    return jsonify(res)


@app.route("/api/admin/users", methods=["POST"])
@require_auth
def admin_create_user():
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = data.get("phone") or ""
    city = data.get("city") or ""

    if not name or not email:
        return jsonify({"error": "Name and email are required"}), 400

    db = get_db()
    exists = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if exists:
        return jsonify({"error": "User with this email already exists"}), 400

    cur = db.execute(
        "INSERT INTO users (name, email, phone, city, status) VALUES (?, ?, ?, ?, 'ACTIVE')",
        (name, email, phone, city)
    )
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "CREATE_USER", "Users", notes=f"Created customer {email}")
    created = dict(db.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone())
    return jsonify(created), 201


@app.route("/api/admin/users/<int:id>", methods=["PATCH"])
@require_auth
def admin_update_user_status(id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in ["ACTIVE", "DISABLED"]:
        return jsonify({"error": "Invalid status"}), 400

    db = get_db()
    db.execute("UPDATE users SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, id))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "UPDATE_USER_STATUS", "Users", notes=f"Set user {id} to {status}")
    return jsonify({"success": True})


@app.route("/api/admin/users/<int:id>", methods=["DELETE"])
@require_auth
def admin_delete_user(id):
    db = get_db()
    db.execute("DELETE FROM users WHERE id = ?", (id,))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "DELETE_USER", "Users", notes=f"Deleted user {id}")
    return jsonify({"success": True})


# ══════════════════════════════════════════════════════════════════
# GOLD RATES CRUD & HISTORY
# ══════════════════════════════════════════════════════════════════

@app.route("/api/gold-rates", methods=["GET"])
@app.route("/api/admin/gold-rates", methods=["GET"])
def get_gold_rates():
    data = fetch_live_gold_rates()
    return jsonify(data)


@app.route("/api/admin/gold-rates/refresh", methods=["POST"])
@require_auth
def admin_refresh_gold_rates():
    global cached_gold_data, last_gold_fetch
    cached_gold_data = None
    last_gold_fetch = 0
    data = fetch_live_gold_rates()

    # Log to history
    db = get_db()
    db.execute("""
        INSERT INTO gold_rate_history (rate_24k, rate_22k, rate_18k, change_amount, change_percent, source)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (data["rate24k"], data["rate22k"], data["rate18k"], data["change24k"], data["changePercent"], data["provider"]))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "REFRESH_GOLD_RATES", "Gold Rates", notes=f"22k: {data['rate22k']}")

    return jsonify(data)


@app.route("/api/admin/gold-rates/history", methods=["GET"])
@require_auth
def admin_get_gold_rate_history():
    db = get_db()
    rows = db.execute("SELECT * FROM gold_rate_history ORDER BY recorded_at DESC LIMIT 50").fetchall()
    return jsonify(list_from_rows(rows))


@app.route("/api/admin/gold-rates/override", methods=["PATCH"])
@require_auth
def admin_override_gold_rates():
    data = request.get_json(silent=True) or {}
    is_manual = "1" if data.get("is_manual") in [True, 1, "1", "true"] else "0"
    rate_22k = str(data.get("rate_22k") or 7250)
    rate_24k = str(data.get("rate_24k") or 7910)

    db = get_db()
    for k, v in [("gold_is_manual", is_manual), ("gold_manual_22k", rate_22k), ("gold_manual_24k", rate_24k)]:
        db.execute("""
            INSERT INTO site_settings (setting_key, setting_value, updated_by)
            VALUES (?, ?, ?)
            ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value, updated_at=CURRENT_TIMESTAMP
        """, (k, v, g.current_admin["id"]))
    db.commit()

    global cached_gold_data, last_gold_fetch
    cached_gold_data = None
    last_gold_fetch = 0

    log_action(g.current_admin["id"], g.current_admin["email"], "OVERRIDE_GOLD_RATES", "Gold Rates", notes=f"Manual={is_manual}, 22k={rate_22k}")
    return jsonify({"success": True, "rates": fetch_live_gold_rates()})


# ══════════════════════════════════════════════════════════════════
# ADMIN ACCOUNTS, SITE SETTINGS, & LOGS (SUPER ADMIN)
# ══════════════════════════════════════════════════════════════════

@app.route("/api/admin/admins", methods=["GET"])
@require_auth
@require_super_admin
def admin_get_admins():
    db = get_db()
    rows = db.execute("SELECT id, name, email, role, status, last_login, created_at, updated_at FROM admins ORDER BY id ASC").fetchall()
    return jsonify(list_from_rows(rows))


@app.route("/api/admin/admins", methods=["POST"])
@require_auth
@require_super_admin
def admin_create_admin():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = data.get("role", "ADMIN")

    if not name or not email or not password:
        return jsonify({"error": "Name, email and password are required"}), 400

    db = get_db()
    exists = db.execute("SELECT id FROM admins WHERE email = ?", (email,)).fetchone()
    if exists:
        return jsonify({"error": "An admin with this email already exists"}), 400

    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")
    cur = db.execute(
        "INSERT INTO admins (name, email, password_hash, role, status) VALUES (?, ?, ?, ?, 'ACTIVE')",
        (name, email, pw_hash, role)
    )
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "CREATE_ADMIN", "Admin Accounts", notes=f"Created {email}")
    created = dict(db.execute("SELECT id, name, email, role, status, created_at FROM admins WHERE id = ?", (cur.lastrowid,)).fetchone())
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
    db.execute("UPDATE admins SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, id))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], f"SET_ADMIN_{status}", "Admin Accounts", notes=f"Admin {id}")
    return jsonify({"success": True})


@app.route("/api/admin/admins/<int:id>/reset-password", methods=["POST"])
@require_auth
@require_super_admin
def admin_reset_password(id):
    data = request.get_json(silent=True) or {}
    new_pw = data.get("new_password") or ""
    if not new_pw or len(new_pw) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    db = get_db()
    pw_hash = bcrypt.hashpw(new_pw.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")
    db.execute("UPDATE admins SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (pw_hash, id))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "RESET_ADMIN_PASSWORD", "Admin Accounts", notes=f"Admin {id}")
    return jsonify({"success": True})


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
            ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value, updated_at=CURRENT_TIMESTAMP
        """, (key, str(val), g.current_admin["id"]))
    db.commit()
    log_action(g.current_admin["id"], g.current_admin["email"], "UPDATE_SETTINGS", "Site Settings")
    return jsonify({"success": True})


@app.route("/api/admin/logs", methods=["GET"])
@require_auth
@require_super_admin
def admin_get_logs():
    page = max(1, int(request.args.get("page", 1)))
    limit = min(100, int(request.args.get("limit", 50)))
    offset = (page - 1) * limit
    search = request.args.get("search", "").strip()
    action = request.args.get("action", "").strip()
    status = request.args.get("status", "").strip()

    where = ["1=1"]
    params = []
    if search:
        where.append("(admin_email LIKE ? OR action LIKE ? OR module LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    if action:
        where.append("action = ?")
        params.append(action)
    if status:
        where.append("status = ?")
        params.append(status)

    where_str = " AND ".join(where)
    db = get_db()
    total = db.execute(f"SELECT COUNT(*) as c FROM admin_access_logs WHERE {where_str}", params).fetchone()["c"]
    rows = db.execute(f"""
        SELECT * FROM admin_access_logs
        WHERE {where_str}
        ORDER BY created_at DESC
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
    rows = db.execute("SELECT DISTINCT action FROM admin_access_logs ORDER BY action ASC").fetchall()
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    print(f"\n👑 THE 22KT GOLD Server running at http://localhost:{port}")
    print(f"📡 Admin Panel:  http://localhost:{port}/admin-login.html")
    print(f"💛 Gold Rate API: http://localhost:{port}/api/gold-rates")
    print(f"💾 Database:     {'PostgreSQL' if USE_POSTGRES else f'SQLite ({DB_PATH.name})'}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
