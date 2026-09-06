// backend/routes/orders.routes.js — Full orders CRUD

const express = require('express');
const db      = require('../db');
const { requireAuth, logAction } = require('../auth');

const router = express.Router();

const ORDER_STATUSES   = ['Pending Payment','Confirmed','Processing','In Production','Ready','Shipped','Delivered','Cancelled'];
const PAYMENT_STATUSES = ['Pending','Paid','Refunded','Failed'];

// GET /api/admin/orders — list with search/filter/pagination
router.get('/', requireAuth, async (req, res) => {
    try {
        const page     = Math.max(1, parseInt(req.query.page  || '1'));
        const limit    = Math.min(100, parseInt(req.query.limit || '20'));
        const offset   = (page - 1) * limit;
        const search   = req.query.search  || '';
        const status   = req.query.status  || '';
        const payment  = req.query.payment || '';
        const dateFrom = req.query.dateFrom || '';
        const dateTo   = req.query.dateTo   || '';
        const sort     = ['created_at','total_amount','customer_name'].includes(req.query.sort) ? req.query.sort : 'created_at';
        const dir      = req.query.dir === 'asc' ? 'ASC' : 'DESC';

        let where = ['1=1'];
        let params = [];

        if (search) {
            where.push('(order_number LIKE ? OR customer_name LIKE ? OR customer_email LIKE ?)');
            const like = `%${search}%`;
            params.push(like, like, like);
        }
        if (status && ORDER_STATUSES.includes(status)) {
            where.push('order_status = ?');
            params.push(status);
        }
        if (payment && PAYMENT_STATUSES.includes(payment)) {
            where.push('payment_status = ?');
            params.push(payment);
        }
        if (dateFrom) {
            where.push('DATE(created_at) >= ?');
            params.push(dateFrom);
        }
        if (dateTo) {
            where.push('DATE(created_at) <= ?');
            params.push(dateTo);
        }

        const whereStr = where.join(' AND ');

        const [[{ total }]] = await db.query(`SELECT COUNT(*) as total FROM orders WHERE ${whereStr}`, params);
        const [rows]        = await db.query(
            `SELECT * FROM orders WHERE ${whereStr} ORDER BY ${sort} ${dir} LIMIT ? OFFSET ?`,
            [...params, limit, offset]
        );

        res.json({ orders: rows, total, page, limit, pages: Math.ceil(total / limit) });
    } catch (err) {
        console.error('Orders list error:', err);
        res.status(500).json({ error: 'Failed to load orders' });
    }
});

// GET /api/admin/orders/:id
router.get('/:id', requireAuth, async (req, res) => {
    try {
        const [rows] = await db.query('SELECT * FROM orders WHERE id = ?', [req.params.id]);
        if (!rows.length) return res.status(404).json({ error: 'Order not found' });
        res.json(rows[0]);
    } catch (err) {
        res.status(500).json({ error: 'Failed to load order' });
    }
});

// PATCH /api/admin/orders/:id — update status / payment_status / notes
router.patch('/:id', requireAuth, async (req, res) => {
    const { order_status, payment_status, notes } = req.body;
    try {
        const [check] = await db.query('SELECT id FROM orders WHERE id = ?', [req.params.id]);
        if (!check.length) return res.status(404).json({ error: 'Order not found' });

        const updates = [];
        const params  = [];

        if (order_status) {
            if (!ORDER_STATUSES.includes(order_status)) return res.status(400).json({ error: 'Invalid order status' });
            updates.push('order_status = ?');
            params.push(order_status);
        }
        if (payment_status) {
            if (!PAYMENT_STATUSES.includes(payment_status)) return res.status(400).json({ error: 'Invalid payment status' });
            updates.push('payment_status = ?');
            params.push(payment_status);
        }
        if (notes !== undefined) {
            updates.push('notes = ?');
            params.push(notes);
        }

        if (!updates.length) return res.status(400).json({ error: 'Nothing to update' });

        params.push(req.params.id);
        await db.query(`UPDATE orders SET ${updates.join(', ')}, updated_at = NOW() WHERE id = ?`, params);

        await logAction(req.admin.id, req.admin.email, 'UPDATE_ORDER', 'Orders', req);

        const [updated] = await db.query('SELECT * FROM orders WHERE id = ?', [req.params.id]);
        res.json(updated[0]);
    } catch (err) {
        console.error('Order update error:', err);
        res.status(500).json({ error: 'Failed to update order' });
    }
});

// DELETE /api/admin/orders/:id — archive (soft delete via status=Cancelled)
router.delete('/:id', requireAuth, async (req, res) => {
    try {
        const [check] = await db.query('SELECT id FROM orders WHERE id = ?', [req.params.id]);
        if (!check.length) return res.status(404).json({ error: 'Order not found' });
        await db.query(`UPDATE orders SET order_status = 'Cancelled', updated_at = NOW() WHERE id = ?`, [req.params.id]);
        await logAction(req.admin.id, req.admin.email, 'CANCEL_ORDER', 'Orders', req);
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: 'Failed to cancel order' });
    }
});

module.exports = router;
