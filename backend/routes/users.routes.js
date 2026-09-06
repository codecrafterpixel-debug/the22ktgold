// backend/routes/users.routes.js — Customer users management

const express = require('express');
const db      = require('../db');
const { requireAuth, logAction } = require('../auth');

const router = express.Router();

// GET /api/admin/users
router.get('/', requireAuth, async (req, res) => {
    try {
        const page   = Math.max(1, parseInt(req.query.page  || '1'));
        const limit  = Math.min(100, parseInt(req.query.limit || '20'));
        const offset = (page - 1) * limit;
        const search = req.query.search || '';
        const status = req.query.status || '';
        const sort   = ['created_at','name','email'].includes(req.query.sort) ? req.query.sort : 'created_at';
        const dir    = req.query.dir === 'asc' ? 'ASC' : 'DESC';

        let where  = ['1=1'];
        let params = [];

        if (search) {
            where.push('(name LIKE ? OR email LIKE ? OR phone LIKE ?)');
            const like = `%${search}%`;
            params.push(like, like, like);
        }
        if (status === 'ACTIVE' || status === 'DISABLED') {
            where.push('u.status = ?');
            params.push(status);
        }

        const whereStr = where.join(' AND ');

        const [[{ total }]] = await db.query(
            `SELECT COUNT(*) as total FROM users u WHERE ${whereStr}`, params
        );

        const [rows] = await db.query(`
            SELECT u.*,
                   COUNT(o.id)          as order_count,
                   COALESCE(SUM(o.total_amount), 0) as total_spent
            FROM users u
            LEFT JOIN orders o ON o.user_id = u.id
            WHERE ${whereStr}
            GROUP BY u.id
            ORDER BY ${sort} ${dir}
            LIMIT ? OFFSET ?
        `, [...params, limit, offset]);

        res.json({ users: rows, total, page, limit, pages: Math.ceil(total / limit) });
    } catch (err) {
        console.error('Users list error:', err);
        res.status(500).json({ error: 'Failed to load users' });
    }
});

// GET /api/admin/users/:id
router.get('/:id', requireAuth, async (req, res) => {
    try {
        const [rows] = await db.query(
            `SELECT u.*, COUNT(o.id) as order_count, COALESCE(SUM(o.total_amount),0) as total_spent
             FROM users u LEFT JOIN orders o ON o.user_id = u.id
             WHERE u.id = ? GROUP BY u.id`,
            [req.params.id]
        );
        if (!rows.length) return res.status(404).json({ error: 'User not found' });

        const [orders] = await db.query(
            'SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 20',
            [req.params.id]
        );

        res.json({ user: rows[0], orders });
    } catch (err) {
        res.status(500).json({ error: 'Failed to load user' });
    }
});

// PATCH /api/admin/users/:id — enable/disable
router.patch('/:id', requireAuth, async (req, res) => {
    const { status } = req.body;
    if (!['ACTIVE','DISABLED'].includes(status)) {
        return res.status(400).json({ error: 'Invalid status' });
    }
    try {
        await db.query('UPDATE users SET status = ?, updated_at = NOW() WHERE id = ?', [status, req.params.id]);
        await logAction(req.admin.id, req.admin.email, `${status === 'ACTIVE' ? 'ENABLE' : 'DISABLE'}_USER`, 'Users', req);
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: 'Failed to update user' });
    }
});

// DELETE /api/admin/users/:id
router.delete('/:id', requireAuth, async (req, res) => {
    try {
        // Check user has no active orders
        const [[{ cnt }]] = await db.query(
            `SELECT COUNT(*) as cnt FROM orders WHERE user_id = ? AND order_status NOT IN ('Delivered','Cancelled')`,
            [req.params.id]
        );
        if (cnt > 0) {
            return res.status(400).json({ error: 'Cannot delete user with active orders' });
        }
        await db.query('DELETE FROM users WHERE id = ?', [req.params.id]);
        await logAction(req.admin.id, req.admin.email, 'DELETE_USER', 'Users', req);
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: 'Failed to delete user' });
    }
});

module.exports = router;
