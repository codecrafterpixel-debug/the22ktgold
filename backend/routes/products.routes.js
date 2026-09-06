// backend/routes/products.routes.js — Full product CRUD with image upload

const express = require('express');
const multer  = require('multer');
const path    = require('path');
const db      = require('../db');
const { requireAuth, logAction } = require('../auth');

const router = express.Router();

// ── Multer memory storage (required for Vercel — no persistent filesystem) ──
const upload = multer({
    storage: multer.memoryStorage(),
    limits: { fileSize: 5 * 1024 * 1024 }, // 5 MB
    fileFilter: (req, file, cb) => {
        const allowed = ['.jpg','.jpeg','.png','.webp'];
        if (allowed.includes(path.extname(file.originalname).toLowerCase())) {
            cb(null, true);
        } else {
            cb(new Error('Only JPG, PNG, WebP images are allowed'));
        }
    }
});

function makeSlug(str) {
    return str.toLowerCase().trim()
        .replace(/[^a-z0-9\s-]/g, '')
        .replace(/\s+/g, '-')
        .replace(/-+/g, '-');
}

// GET /api/admin/products
router.get('/', requireAuth, async (req, res) => {
    try {
        const page     = Math.max(1, parseInt(req.query.page  || '1'));
        const limit    = Math.min(100, parseInt(req.query.limit || '20'));
        const offset   = (page - 1) * limit;
        const search   = req.query.search   || '';
        const category = req.query.category || '';
        const active   = req.query.active;
        const featured = req.query.featured;

        let where = ['1=1'], params = [];

        if (search) {
            where.push('(p.name LIKE ? OR p.sku LIKE ?)');
            params.push(`%${search}%`, `%${search}%`);
        }
        if (category) {
            where.push('p.category_id = ?');
            params.push(category);
        }
        if (active !== undefined && active !== '') {
            where.push('p.active = ?');
            params.push(active === '1' || active === 'true' ? 1 : 0);
        }
        if (featured !== undefined && featured !== '') {
            where.push('p.featured = ?');
            params.push(featured === '1' || featured === 'true' ? 1 : 0);
        }

        const whereStr = where.join(' AND ');
        const [[{ total }]] = await db.query(`SELECT COUNT(*) as total FROM products p WHERE ${whereStr}`, params);

        const [rows] = await db.query(`
            SELECT p.*, c.name as category_name,
                   (SELECT image_url FROM product_images pi WHERE pi.product_id = p.id AND pi.is_primary = 1 LIMIT 1) as primary_image
            FROM products p
            LEFT JOIN categories c ON c.id = p.category_id
            WHERE ${whereStr}
            ORDER BY p.created_at DESC
            LIMIT ? OFFSET ?
        `, [...params, limit, offset]);

        res.json({ products: rows, total, page, limit, pages: Math.ceil(total / limit) });
    } catch (err) {
        console.error('Products list error:', err);
        res.status(500).json({ error: 'Failed to load products' });
    }
});

// GET /api/admin/products/:id
router.get('/:id', requireAuth, async (req, res) => {
    try {
        const [rows] = await db.query(`
            SELECT p.*, c.name as category_name
            FROM products p LEFT JOIN categories c ON c.id = p.category_id
            WHERE p.id = ?
        `, [req.params.id]);
        if (!rows.length) return res.status(404).json({ error: 'Product not found' });

        const [images] = await db.query(
            'SELECT * FROM product_images WHERE product_id = ? ORDER BY is_primary DESC',
            [req.params.id]
        );
        res.json({ ...rows[0], images });
    } catch (err) {
        res.status(500).json({ error: 'Failed to load product' });
    }
});

// POST /api/admin/products
router.post('/', requireAuth, upload.single('image'), async (req, res) => {
    const { name, category_id, description, purity, weight, making_charges, base_price, current_price, stock, sku, featured, active } = req.body;

    if (!name || !name.trim())   return res.status(400).json({ error: 'Product name is required' });
    if (!purity)                 return res.status(400).json({ error: 'Purity is required' });
    if (!weight || weight <= 0)  return res.status(400).json({ error: 'Valid weight is required' });

    const slug = makeSlug(name);

    try {
        const [exists] = await db.query('SELECT id FROM products WHERE slug = ?', [slug]);
        if (exists.length) return res.status(400).json({ error: 'A product with this name already exists' });

        const [result] = await db.query(
            `INSERT INTO products (name, slug, category_id, description, purity, weight, making_charges, base_price, current_price, stock, sku, featured, active)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)`,
            [
                name.trim(), slug,
                category_id || null,
                description || null,
                parseInt(purity),
                parseFloat(weight),
                parseFloat(making_charges || 0),
                parseFloat(base_price || 0),
                parseFloat(current_price || 0),
                parseInt(stock || 0),
                sku || null,
                featured === 'true' || featured === '1' ? 1 : 0,
                active === 'false' || active === '0' ? 0 : 1
            ]
        );

        // Save image as base64 data URL (works on Vercel — no disk needed)
        if (req.file) {
            const b64 = `data:${req.file.mimetype};base64,${req.file.buffer.toString('base64')}`;
            await db.query(
                'INSERT INTO product_images (product_id, image_url, is_primary) VALUES (?,?,1)',
                [result[0].insertId, b64]
            );
        }

        await logAction(req.admin.id, req.admin.email, 'CREATE_PRODUCT', 'Products', req);

        const [product] = await db.query('SELECT * FROM products WHERE id = ?', [result.insertId]);
        res.status(201).json(product[0]);
    } catch (err) {
        console.error('Create product error:', err);
        res.status(500).json({ error: 'Failed to create product' });
    }
});

// PUT /api/admin/products/:id
router.put('/:id', requireAuth, upload.single('image'), async (req, res) => {
    const { name, category_id, description, purity, weight, making_charges, base_price, current_price, stock, sku, featured, active } = req.body;

    if (!name || !name.trim()) return res.status(400).json({ error: 'Product name is required' });

    try {
        const [check] = await db.query('SELECT id FROM products WHERE id = ?', [req.params.id]);
        if (!check.length) return res.status(404).json({ error: 'Product not found' });

        const slug = makeSlug(name);
        const [exists] = await db.query('SELECT id FROM products WHERE slug = ? AND id != ?', [slug, req.params.id]);
        if (exists.length) return res.status(400).json({ error: 'A product with this name already exists' });

        await db.query(
            `UPDATE products SET name=?, slug=?, category_id=?, description=?, purity=?, weight=?, making_charges=?,
             base_price=?, current_price=?, stock=?, sku=?, featured=?, active=?, updated_at=NOW() WHERE id=?`,
            [
                name.trim(), slug,
                category_id || null, description || null,
                parseInt(purity || 22), parseFloat(weight || 0),
                parseFloat(making_charges || 0), parseFloat(base_price || 0), parseFloat(current_price || 0),
                parseInt(stock || 0), sku || null,
                featured === 'true' || featured === '1' ? 1 : 0,
                active === 'false' || active === '0' ? 0 : 1,
                req.params.id
            ]
        );

        if (req.file) {
            // Remove old primary image, add new (base64 data URL for Vercel)
            const b64 = `data:${req.file.mimetype};base64,${req.file.buffer.toString('base64')}`;
            await db.query('UPDATE product_images SET is_primary = 0 WHERE product_id = ?', [req.params.id]);
            await db.query(
                'INSERT INTO product_images (product_id, image_url, is_primary) VALUES (?,?,1)',
                [req.params.id, b64]
            );
        }

        await logAction(req.admin.id, req.admin.email, 'UPDATE_PRODUCT', 'Products', req);
        const [updated] = await db.query('SELECT * FROM products WHERE id = ?', [req.params.id]);
        res.json(updated[0]);
    } catch (err) {
        console.error('Update product error:', err);
        res.status(500).json({ error: 'Failed to update product' });
    }
});

// DELETE /api/admin/products/:id
router.delete('/:id', requireAuth, async (req, res) => {
    try {
        const [check] = await db.query('SELECT id FROM products WHERE id = ?', [req.params.id]);
        if (!check.length) return res.status(404).json({ error: 'Product not found' });

        await db.query('DELETE FROM product_images WHERE product_id = ?', [req.params.id]);
        await db.query('DELETE FROM products WHERE id = ?', [req.params.id]);
        await logAction(req.admin.id, req.admin.email, 'DELETE_PRODUCT', 'Products', req);
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: 'Failed to delete product' });
    }
});

module.exports = router;
