// backend/routes/custom-orders.routes.js — Custom jewellery request management

const express = require('express');
const db      = require('../db');
const { requireAuth, logAction } = require('../auth');

const router = express.Router();

const VALID_STATUSES = ['New','Reviewing','Contacted','Designing','Quoted','Approved','In Production','Completed','Rejected'];

// GET /api/admin/custom-orders
router.get('/', requireAuth, async (req, res) => {
    try {
        const page   = Math.max(1, parseInt(req.query.page  || '1'));
        const limit  = Math.min(100, parseInt(req.query.limit || '20'));
        const offset = (page - 1) * limit;
        const search = req.query.search || '';
        const status = req.query.status || '';

        let where = ['1=1'], params = [];
        if (search) {
            where.push('(name LIKE ? OR email LIKE ? OR jewellery_type LIKE ?)');
            const like = `%${search}%`;
            params.push(like, like, like);
        }
        if (status && VALID_STATUSES.includes(status)) {
            where.push('status = ?');
            params.push(status);
        }

        const [[{ total }]] = await db.query(
            `SELECT COUNT(*) as total FROM custom_orders WHERE ${where.join(' AND ')}`, params
        );
        const [rows] = await db.query(
            `SELECT * FROM custom_orders WHERE ${where.join(' AND ')} ORDER BY created_at DESC LIMIT ? OFFSET ?`,
            [...params, limit, offset]
        );

        res.json({ customOrders: rows, total, page, limit, pages: Math.ceil(total / limit) });
    } catch (err) {
        res.status(500).json({ error: 'Failed to load custom orders' });
    }
});

// GET /api/admin/custom-orders/:id
router.get('/:id', requireAuth, async (req, res) => {
    try {
        const [rows] = await db.query('SELECT * FROM custom_orders WHERE id = ?', [req.params.id]);
        if (!rows.length) return res.status(404).json({ error: 'Custom order not found' });
        res.json(rows[0]);
    } catch (err) {
        res.status(500).json({ error: 'Failed to load custom order' });
    }
});

// PATCH /api/admin/custom-orders/:id
router.patch('/:id', requireAuth, async (req, res) => {
    const { status, admin_notes, quote_amount } = req.body;
    if (status && !VALID_STATUSES.includes(status)) {
        return res.status(400).json({ error: 'Invalid status' });
    }
    try {
        const updates = [], params = [];
        if (status)        { updates.push('status = ?');       params.push(status); }
        if (admin_notes !== undefined) { updates.push('admin_notes = ?'); params.push(admin_notes); }
        if (quote_amount !== undefined) {
            const q = parseFloat(quote_amount);
            if (isNaN(q)) return res.status(400).json({ error: 'Invalid quote amount' });
            updates.push('quote_amount = ?');
            params.push(q);
        }
        if (!updates.length) return res.status(400).json({ error: 'Nothing to update' });

        params.push(req.params.id);
        await db.query(`UPDATE custom_orders SET ${updates.join(', ')}, updated_at = NOW() WHERE id = ?`, params);
        await logAction(req.admin.id, req.admin.email, 'UPDATE_CUSTOM_ORDER', 'Custom Orders', req);
        const [updated] = await db.query('SELECT * FROM custom_orders WHERE id = ?', [req.params.id]);
        res.json(updated[0]);
    } catch (err) {
        res.status(500).json({ error: 'Failed to update custom order' });
    }
});

// DELETE /api/admin/custom-orders/:id
router.delete('/:id', requireAuth, async (req, res) => {
    try {
        await db.query("UPDATE custom_orders SET status = 'Rejected', updated_at = NOW() WHERE id = ?", [req.params.id]);
        await logAction(req.admin.id, req.admin.email, 'REJECT_CUSTOM_ORDER', 'Custom Orders', req);
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: 'Failed to update custom order' });
    }
});

module.exports = router;
