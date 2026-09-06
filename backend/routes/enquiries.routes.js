// backend/routes/enquiries.routes.js — Enquiry management

const express = require('express');
const db      = require('../db');
const { requireAuth, logAction } = require('../auth');

const router = express.Router();

const VALID_STATUSES = ['New','Contacted','In Progress','Resolved','Closed'];

// GET /api/admin/enquiries
router.get('/', requireAuth, async (req, res) => {
    try {
        const page   = Math.max(1, parseInt(req.query.page  || '1'));
        const limit  = Math.min(100, parseInt(req.query.limit || '20'));
        const offset = (page - 1) * limit;
        const search = req.query.search || '';
        const status = req.query.status || '';

        let where = ['1=1'], params = [];
        if (search) {
            where.push('(name LIKE ? OR email LIKE ? OR phone LIKE ?)');
            const like = `%${search}%`;
            params.push(like, like, like);
        }
        if (status && VALID_STATUSES.includes(status)) {
            where.push('status = ?');
            params.push(status);
        }

        const [[{ total }]] = await db.query(`SELECT COUNT(*) as total FROM enquiries WHERE ${where.join(' AND ')}`, params);
        const [rows] = await db.query(
            `SELECT * FROM enquiries WHERE ${where.join(' AND ')} ORDER BY created_at DESC LIMIT ? OFFSET ?`,
            [...params, limit, offset]
        );

        res.json({ enquiries: rows, total, page, limit, pages: Math.ceil(total / limit) });
    } catch (err) {
        res.status(500).json({ error: 'Failed to load enquiries' });
    }
});

// GET /api/admin/enquiries/:id
router.get('/:id', requireAuth, async (req, res) => {
    try {
        const [rows] = await db.query('SELECT * FROM enquiries WHERE id = ?', [req.params.id]);
        if (!rows.length) return res.status(404).json({ error: 'Enquiry not found' });
        res.json(rows[0]);
    } catch (err) {
        res.status(500).json({ error: 'Failed to load enquiry' });
    }
});

// PATCH /api/admin/enquiries/:id
router.patch('/:id', requireAuth, async (req, res) => {
    const { status, admin_notes } = req.body;
    if (status && !VALID_STATUSES.includes(status)) {
        return res.status(400).json({ error: 'Invalid status' });
    }
    try {
        const updates = [], params = [];
        if (status)        { updates.push('status = ?');      params.push(status); }
        if (admin_notes !== undefined) { updates.push('admin_notes = ?'); params.push(admin_notes); }
        if (!updates.length) return res.status(400).json({ error: 'Nothing to update' });

        params.push(req.params.id);
        await db.query(`UPDATE enquiries SET ${updates.join(', ')}, updated_at = NOW() WHERE id = ?`, params);
        await logAction(req.admin.id, req.admin.email, 'UPDATE_ENQUIRY', 'Enquiries', req);
        const [updated] = await db.query('SELECT * FROM enquiries WHERE id = ?', [req.params.id]);
        res.json(updated[0]);
    } catch (err) {
        res.status(500).json({ error: 'Failed to update enquiry' });
    }
});

// DELETE /api/admin/enquiries/:id
router.delete('/:id', requireAuth, async (req, res) => {
    try {
        await db.query('DELETE FROM enquiries WHERE id = ?', [req.params.id]);
        await logAction(req.admin.id, req.admin.email, 'DELETE_ENQUIRY', 'Enquiries', req);
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: 'Failed to delete enquiry' });
    }
});

module.exports = router;
