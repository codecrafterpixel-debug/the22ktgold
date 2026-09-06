-- THE 22KT GOLD — PostgreSQL Schema (for Neon Database)
-- Run this file in your Neon SQL Editor

-- ─────────────────────────────────────────────
-- ADMINS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admins (
  id            SERIAL PRIMARY KEY,
  name          VARCHAR(120) NOT NULL,
  email         VARCHAR(200) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role          VARCHAR(20) NOT NULL DEFAULT 'ADMIN' CHECK (role IN ('ADMIN','SUPER_ADMIN')),
  status        VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','DISABLED')),
  last_login    TIMESTAMP NULL,
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_admins_email ON admins(email);
CREATE INDEX IF NOT EXISTS idx_admins_role  ON admins(role);
CREATE INDEX IF NOT EXISTS idx_admins_status ON admins(status);

-- ─────────────────────────────────────────────
-- ADMIN ACCESS LOGS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admin_access_logs (
  id          SERIAL PRIMARY KEY,
  admin_id    INTEGER NULL REFERENCES admins(id) ON DELETE SET NULL,
  admin_email VARCHAR(200) NULL,
  action      VARCHAR(80)  NOT NULL,
  module      VARCHAR(60)  NOT NULL,
  ip_address  VARCHAR(60)  NULL,
  user_agent  TEXT         NULL,
  status      VARCHAR(20) NOT NULL DEFAULT 'SUCCESS' CHECK (status IN ('SUCCESS','FAILURE')),
  notes       TEXT         NULL,
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_logs_admin_id   ON admin_access_logs(admin_id);
CREATE INDEX IF NOT EXISTS idx_logs_action     ON admin_access_logs(action);
CREATE INDEX IF NOT EXISTS idx_logs_module     ON admin_access_logs(module);
CREATE INDEX IF NOT EXISTS idx_logs_created_at ON admin_access_logs(created_at);

-- ─────────────────────────────────────────────
-- SITE SETTINGS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS site_settings (
  id            SERIAL PRIMARY KEY,
  setting_key   VARCHAR(100) NOT NULL UNIQUE,
  setting_value TEXT NULL,
  updated_by    INTEGER NULL REFERENCES admins(id) ON DELETE SET NULL,
  updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_settings_key ON site_settings(setting_key);

-- ─────────────────────────────────────────────
-- USERS (customers)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
  id         SERIAL PRIMARY KEY,
  name       VARCHAR(200) NOT NULL,
  email      VARCHAR(200) NOT NULL UNIQUE,
  phone      VARCHAR(20)  NULL,
  status     VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','DISABLED')),
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_email  ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);

-- ─────────────────────────────────────────────
-- CATEGORIES
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS categories (
  id          SERIAL PRIMARY KEY,
  name        VARCHAR(120) NOT NULL,
  slug        VARCHAR(140) NOT NULL UNIQUE,
  description TEXT NULL,
  image       VARCHAR(255) NULL,
  active      BOOLEAN NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_categories_slug   ON categories(slug);
CREATE INDEX IF NOT EXISTS idx_categories_active ON categories(active);

-- ─────────────────────────────────────────────
-- PRODUCTS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS products (
  id              SERIAL PRIMARY KEY,
  name            VARCHAR(200) NOT NULL,
  slug            VARCHAR(220) NOT NULL UNIQUE,
  category_id     INTEGER NULL REFERENCES categories(id) ON DELETE SET NULL,
  description     TEXT NULL,
  purity          SMALLINT NOT NULL DEFAULT 22,
  weight          DECIMAL(8,3) NOT NULL DEFAULT 0,
  making_charges  DECIMAL(10,2) NOT NULL DEFAULT 0,
  base_price      DECIMAL(12,2) NOT NULL DEFAULT 0,
  current_price   DECIMAL(12,2) NOT NULL DEFAULT 0,
  stock           INTEGER NOT NULL DEFAULT 0,
  sku             VARCHAR(80) NULL UNIQUE,
  featured        BOOLEAN NOT NULL DEFAULT FALSE,
  active          BOOLEAN NOT NULL DEFAULT TRUE,
  created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_products_active   ON products(active);
CREATE INDEX IF NOT EXISTS idx_products_featured ON products(featured);
CREATE INDEX IF NOT EXISTS idx_products_sku      ON products(sku);

-- ─────────────────────────────────────────────
-- PRODUCT IMAGES
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS product_images (
  id         SERIAL PRIMARY KEY,
  product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  image_url  VARCHAR(255) NOT NULL,
  is_primary BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pimages_product  ON product_images(product_id);
CREATE INDEX IF NOT EXISTS idx_pimages_primary  ON product_images(is_primary);

-- ─────────────────────────────────────────────
-- ORDERS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
  id             SERIAL PRIMARY KEY,
  order_number   VARCHAR(30) NOT NULL UNIQUE,
  user_id        INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
  customer_name  VARCHAR(200) NOT NULL,
  customer_phone VARCHAR(20)  NULL,
  customer_email VARCHAR(200) NULL,
  address        TEXT NULL,
  product_id     INTEGER NULL REFERENCES products(id) ON DELETE SET NULL,
  product_name   VARCHAR(200) NOT NULL,
  product_image  VARCHAR(255) NULL,
  quantity       INTEGER NOT NULL DEFAULT 1,
  weight         DECIMAL(8,3) NOT NULL DEFAULT 0,
  purity         SMALLINT NOT NULL DEFAULT 22,
  gold_rate_used DECIMAL(10,2) NOT NULL DEFAULT 0,
  making_charges DECIMAL(10,2) NOT NULL DEFAULT 0,
  gst            DECIMAL(10,2) NOT NULL DEFAULT 0,
  discount       DECIMAL(10,2) NOT NULL DEFAULT 0,
  total_amount   DECIMAL(12,2) NOT NULL DEFAULT 0,
  payment_status VARCHAR(20) NOT NULL DEFAULT 'Pending' CHECK (payment_status IN ('Pending','Paid','Refunded','Failed')),
  order_status   VARCHAR(30) NOT NULL DEFAULT 'Pending Payment' CHECK (order_status IN ('Pending Payment','Confirmed','Processing','In Production','Ready','Shipped','Delivered','Cancelled')),
  notes          TEXT NULL,
  created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_orders_user           ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_product        ON orders(product_id);
CREATE INDEX IF NOT EXISTS idx_orders_order_status   ON orders(order_status);
CREATE INDEX IF NOT EXISTS idx_orders_payment_status ON orders(payment_status);
CREATE INDEX IF NOT EXISTS idx_orders_created_at     ON orders(created_at);

-- ─────────────────────────────────────────────
-- ORDER ITEMS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS order_items (
  id         SERIAL PRIMARY KEY,
  order_id   INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  product_id INTEGER NULL REFERENCES products(id) ON DELETE SET NULL,
  name       VARCHAR(200) NOT NULL,
  quantity   INTEGER NOT NULL DEFAULT 1,
  weight     DECIMAL(8,3) NOT NULL DEFAULT 0,
  price      DECIMAL(12,2) NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_oitems_order   ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_oitems_product ON order_items(product_id);

-- ─────────────────────────────────────────────
-- GOLD RATES (current snapshot cache)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS gold_rates (
  id           SERIAL PRIMARY KEY,
  rate_22k     DECIMAL(10,2) NOT NULL,
  rate_24k     DECIMAL(10,2) NOT NULL,
  rate_18k     DECIMAL(10,2) NOT NULL,
  source       VARCHAR(80)   NOT NULL DEFAULT 'API',
  is_manual    BOOLEAN       NOT NULL DEFAULT FALSE,
  manual_22k   DECIMAL(10,2) NULL,
  manual_24k   DECIMAL(10,2) NULL,
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ─────────────────────────────────────────────
-- GOLD RATE HISTORY
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS gold_rate_history (
  id             SERIAL PRIMARY KEY,
  rate_22k       DECIMAL(10,2) NOT NULL,
  rate_24k       DECIMAL(10,2) NOT NULL,
  rate_18k       DECIMAL(10,2) NOT NULL,
  change_amount  DECIMAL(8,2)  NOT NULL DEFAULT 0,
  change_percent DECIMAL(6,3)  NOT NULL DEFAULT 0,
  source         VARCHAR(80)   NOT NULL,
  created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_grh_created_at ON gold_rate_history(created_at);

-- ─────────────────────────────────────────────
-- ENQUIRIES
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS enquiries (
  id          SERIAL PRIMARY KEY,
  name        VARCHAR(200) NOT NULL,
  phone       VARCHAR(20)  NULL,
  email       VARCHAR(200) NULL,
  message     TEXT NOT NULL,
  status      VARCHAR(20) NOT NULL DEFAULT 'New' CHECK (status IN ('New','Contacted','In Progress','Resolved','Closed')),
  admin_notes TEXT NULL,
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_enquiries_status     ON enquiries(status);
CREATE INDEX IF NOT EXISTS idx_enquiries_created_at ON enquiries(created_at);

-- ─────────────────────────────────────────────
-- CUSTOM ORDERS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS custom_orders (
  id              SERIAL PRIMARY KEY,
  name            VARCHAR(200) NOT NULL,
  phone           VARCHAR(20)  NULL,
  email           VARCHAR(200) NULL,
  jewellery_type  VARCHAR(100) NOT NULL,
  description     TEXT NOT NULL,
  weight          DECIMAL(8,3) NULL,
  purity          SMALLINT NULL,
  budget          DECIMAL(12,2) NULL,
  reference_image VARCHAR(255) NULL,
  status          VARCHAR(30) NOT NULL DEFAULT 'New' CHECK (status IN ('New','Reviewing','Contacted','Designing','Quoted','Approved','In Production','Completed','Rejected')),
  quote_amount    DECIMAL(12,2) NULL,
  admin_notes     TEXT NULL,
  created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_custom_status     ON custom_orders(status);
CREATE INDEX IF NOT EXISTS idx_custom_created_at ON custom_orders(created_at);

-- ─────────────────────────────────────────────
-- GALLERY
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS gallery (
  id         SERIAL PRIMARY KEY,
  title      VARCHAR(200) NOT NULL,
  alt_text   VARCHAR(255) NULL,
  image_url  VARCHAR(255) NOT NULL,
  category   VARCHAR(80)  NULL,
  featured   BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_gallery_category ON gallery(category);
CREATE INDEX IF NOT EXISTS idx_gallery_featured ON gallery(featured);

-- ═══════════════════════════════════════════════
-- SEED DATA
-- ═══════════════════════════════════════════════

INSERT INTO admins (name, email, password_hash, role, status) VALUES 
('Super Admin', 'dev@22ktgold.com', '$2b$12$QFq.YKnO4IVW.szZ0I8Gg.3R8oi3o.JQkwnPm7yInIuUjqpPCPaDS', 'SUPER_ADMIN', 'ACTIVE'),
('Admin User', 'admin@22ktgold.com', '$2b$12$5RL8cMzqV4vmSbcCBqNK.uN6CeU0tJ1.e1oAC3OhNJ4mH3QL6CaFS', 'ADMIN', 'ACTIVE')
ON CONFLICT (email) DO NOTHING;

INSERT INTO categories (name, slug, description, image, active) VALUES
('Rings',       'rings',       'Handcrafted 22KT gold rings for every occasion.',       'images/cat-rings.jpg',     TRUE),
('Necklaces',   'necklaces',   'Elegant gold necklaces and chains.',                   'images/cat-necklaces.jpg', TRUE),
('Bangles',     'bangles',     'Timeless gold bangles and kadas.',                     'images/cat-bangles.jpg',   TRUE),
('Earrings',    'earrings',    'Delicate and statement gold earrings.',                'images/cat-earrings.jpg',  TRUE),
('Bridal Sets', 'bridal-sets', 'Complete bridal jewellery collections.',               'images/cat-bridal.jpg',    TRUE),
('Men''s Gold', 'mens-gold',   'Masculine gold chains, bracelets and accessories.',    'images/cat-mens.jpg',      TRUE)
ON CONFLICT (slug) DO NOTHING;

INSERT INTO products (name, slug, category_id, description, purity, weight, making_charges, base_price, current_price, stock, sku, featured, active) VALUES
('Heritage Gold Ring',    'heritage-gold-ring',   1, 'Intricately hand-crafted 22KT gold ring with fine filigree detailing.', 22, 4.200, 500,  0, 0, 10, 'SKU-001', TRUE, TRUE),
('Royal Bridal Necklace', 'royal-bridal-necklace',5, 'Traditional bridal masterpiece handcrafted for your grand wedding.',     22, 48.500,5000, 0, 0,  3, 'SKU-002', TRUE, TRUE),
('Temple Gold Bangles',   'temple-gold-bangles',  3, 'Timeless antique finished 22KT bangles and kadas crafted to perfection.',22, 32.000,3000, 0, 0,  5, 'SKU-003', TRUE, TRUE),
('Classic Men''s Chain',  'classic-mens-chain',   6, 'Durable and elegant 22KT machine-cut & hand-linked gold chain.',        22, 18.300,2000, 0, 0,  8, 'SKU-004', FALSE, TRUE)
ON CONFLICT (slug) DO NOTHING;

INSERT INTO site_settings (setting_key, setting_value) VALUES
('business_name',       'THE 22KT GOLD'),
('business_email',      'info@the22ktgold.com'),
('business_phone',      '+91 98765 00000'),
('business_whatsapp',   '+91 98765 00000'),
('business_address',    'Shop No. 1, Gold Market, Jewellers Street, Mumbai - 400001'),
('business_hours',      'Mon–Sat: 10:00 AM – 8:00 PM, Sun: 11:00 AM – 6:00 PM'),
('website_title',       'THE 22KT GOLD — Premium 22KT Gold Jewellery'),
('meta_description',    'Handcrafted 22KT gold jewellery. Custom orders, bridal sets, rings, necklaces and more.'),
('default_currency',    'INR'),
('default_country',     'India'),
('timezone',            'Asia/Kolkata'),
('contact_email',       'contact@the22ktgold.com'),
('support_phone',       '+91 98765 00001'),
('instagram',           'https://instagram.com/the22ktgold'),
('facebook',            'https://facebook.com/the22ktgold'),
('footer_text',         'Crafted with love. Hallmarked for purity.'),
('copyright_text',      '© 2026 THE 22KT GOLD. All rights reserved.')
ON CONFLICT (setting_key) DO NOTHING;
