// backend/routes/categories.routes.js — Full category CRUD

const express = require('express');
const db      = require('../db');
const { requireAuth, logAction } = require('../auth');

const router = express.Router();

function makeSlug(str) {
    return str.toLowerCase().trim()
        .replace(/[^a-z0-9\s-]/g, '')
        .replace(/\s+/g, '-')
        .replace(/-+/g, '-');
}

// GET /api/admin/categories
router.get('/', requireAuth, async (req, res) => {
    try {
        const search = req.query.search || '';
        let where = ['1=1'], params = [];
        if (search) {
            where.push('c.name LIKE ?');
            params.push(`%${search}%`);
        }
        const [rows] = await db.query(`
            SELECT c.*, COUNT(p.id) as product_count
            FROM categories c
            LEFT JOIN products p ON p.category_id = c.id AND p.active = 1
            WHERE ${where.join(' AND ')}
            GROUP BY c.id
            ORDER BY c.name ASC
        `, params);
        res.json(rows);
    } catch (err) {
        res.status(500).json({ error: 'Failed to load categories' });
    }
});

// POST /api/admin/categories
router.post('/', requireAuth, async (req, res) => {
    const { name, description, image, active } = req.body;
    if (!name || !name.trim()) return res.status(400).json({ error: 'Category name is required' });

    const slug = makeSlug(name);
    try {
        const [exists] = await db.query('SELECT id FROM categories WHERE slug = ?', [slug]);
        if (exists.length) return res.status(400).json({ error: 'A category with this name already exists' });

        const [result] = await db.query(
            'INSERT INTO categories (name, slug, description, image, active) VALUES (?,?,?,?,?)',
            [name.trim(), slug, description || null, image || null, active !== false ? 1 : 0]
        );
        await logAction(req.admin.id, req.admin.email, 'CREATE_CATEGORY', 'Categories', req);
        const [cat] = await db.query('SELECT * FROM categories WHERE id = ?', [result.insertId]);
        res.status(201).json(cat[0]);
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Failed to create category' });
    }
});

// PUT /api/admin/categories/:id
router.put('/:id', requireAuth, async (req, res) => {
    const { name, description, image, active } = req.body;
    if (!name || !name.trim()) return res.status(400).json({ error: 'Category name is required' });

    try {
        const [check] = await db.query('SELECT id FROM categories WHERE id = ?', [req.params.id]);
        if (!check.length) return res.status(404).json({ error: 'Category not found' });

        const slug = makeSlug(name);
        const [exists] = await db.query('SELECT id FROM categories WHERE slug = ? AND id != ?', [slug, req.params.id]);
        if (exists.length) return res.status(400).json({ error: 'A category with this name already exists' });

        await db.query(
            'UPDATE categories SET name=?, slug=?, description=?, image=?, active=?, updated_at=NOW() WHERE id=?',
            [name.trim(), slug, description || null, image || null, active !== false ? 1 : 0, req.params.id]
        );
        await logAction(req.admin.id, req.admin.email, 'UPDATE_CATEGORY', 'Categories', req);
        const [updated] = await db.query('SELECT * FROM categories WHERE id = ?', [req.params.id]);
        res.json(updated[0]);
    } catch (err) {
        res.status(500).json({ error: 'Failed to update category' });
    }
});

// DELETE /api/admin/categories/:id
router.delete('/:id', requireAuth, async (req, res) => {
    try {
        // Check for dependent products
        const [[{ cnt }]] = await db.query(
            'SELECT COUNT(*) as cnt FROM products WHERE category_id = ?',
            [req.params.id]
        );
        if (cnt > 0) {
            return res.status(400).json({
                error: `Cannot delete: ${cnt} product(s) belong to this category. Reassign them first.`
            });
        }
        await db.query('DELETE FROM categories WHERE id = ?', [req.params.id]);
        await logAction(req.admin.id, req.admin.email, 'DELETE_CATEGORY', 'Categories', req);
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: 'Failed to delete category' });
    }
});

module.exports = router;
