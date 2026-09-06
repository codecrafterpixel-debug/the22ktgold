// backend/routes/gallery.routes.js — Gallery image management

const express = require('express');
const multer  = require('multer');
const path    = require('path');
const db      = require('../db');
const { requireAuth, logAction } = require('../auth');

const router = express.Router();

// ── Multer memory storage (required for Vercel — no persistent filesystem) ──
const upload = multer({
    storage: multer.memoryStorage(),
    limits: { fileSize: 8 * 1024 * 1024 }, // 8 MB
    fileFilter: (req, file, cb) => {
        const allowed = ['.jpg','.jpeg','.png','.webp'];
        if (allowed.includes(path.extname(file.originalname).toLowerCase())) cb(null, true);
        else cb(new Error('Only JPG, PNG, WebP images allowed'));
    }
});

// GET /api/admin/gallery
router.get('/', requireAuth, async (req, res) => {
    try {
        const page     = Math.max(1, parseInt(req.query.page  || '1'));
        const limit    = Math.min(100, parseInt(req.query.limit || '24'));
        const offset   = (page - 1) * limit;
        const category = req.query.category || '';
        const featured = req.query.featured;

        let where = ['1=1'], params = [];
        if (category) { where.push('category = ?'); params.push(category); }
        if (featured !== undefined && featured !== '') {
            where.push('featured = ?');
            params.push(featured === '1' || featured === 'true' ? 1 : 0);
        }

        const [[{ total }]] = await db.query(`SELECT COUNT(*) as total FROM gallery WHERE ${where.join(' AND ')}`, params);
        const [rows] = await db.query(
            `SELECT * FROM gallery WHERE ${where.join(' AND ')} ORDER BY created_at DESC LIMIT ? OFFSET ?`,
            [...params, limit, offset]
        );

        res.json({ items: rows, total, page, limit, pages: Math.ceil(total / limit) });
    } catch (err) {
        res.status(500).json({ error: 'Failed to load gallery' });
    }
});

// POST /api/admin/gallery — upload image
router.post('/', requireAuth, upload.single('image'), async (req, res) => {
    if (!req.file) return res.status(400).json({ error: 'Image file is required' });

    const { title, alt_text, category, featured } = req.body;
    if (!title || !title.trim()) return res.status(400).json({ error: 'Title is required' });

    try {
        // Store as base64 data URL (works on Vercel — no disk needed)
        const imageUrl = `data:${req.file.mimetype};base64,${req.file.buffer.toString('base64')}`;
        const [result] = await db.query(
            'INSERT INTO gallery (title, alt_text, image_url, category, featured) VALUES (?,?,?,?,?)',
            [
                title.trim(),
                alt_text || null,
                imageUrl,
                category || null,
                featured === 'true' || featured === '1' ? 1 : 0
            ]
        );
        await logAction(req.admin.id, req.admin.email, 'UPLOAD_GALLERY', 'Gallery', req);
        const [item] = await db.query('SELECT * FROM gallery WHERE id = ?', [result[0].insertId]);
        res.status(201).json(item[0]);
    } catch (err) {
        console.error('Gallery upload error:', err);
        res.status(500).json({ error: 'Failed to upload image' });
    }
});

// PATCH /api/admin/gallery/:id — update metadata
router.patch('/:id', requireAuth, async (req, res) => {
    const { title, alt_text, category, featured } = req.body;
    try {
        await db.query(
            'UPDATE gallery SET title=?, alt_text=?, category=?, featured=? WHERE id=?',
            [title, alt_text || null, category || null, featured ? 1 : 0, req.params.id]
        );
        const [item] = await db.query('SELECT * FROM gallery WHERE id = ?', [req.params.id]);
        res.json(item[0]);
    } catch (err) {
        res.status(500).json({ error: 'Failed to update gallery item' });
    }
});

// DELETE /api/admin/gallery/:id
router.delete('/:id', requireAuth, async (req, res) => {
    try {
        const [rows] = await db.query('SELECT * FROM gallery WHERE id = ?', [req.params.id]);
        if (!rows.length) return res.status(404).json({ error: 'Gallery item not found' });

        await db.query('DELETE FROM gallery WHERE id = ?', [req.params.id]);
        await logAction(req.admin.id, req.admin.email, 'DELETE_GALLERY', 'Gallery', req);
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: 'Failed to delete gallery item' });
    }
});

module.exports = router;
