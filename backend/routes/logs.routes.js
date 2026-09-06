// backend/routes/logs.routes.js — Access logs (SUPER ADMIN ONLY)

const express = require('express');
const db      = require('../db');
const { requireAuth, requireSuperAdmin } = require('../auth');

const router = express.Router();

router.use(requireAuth, requireSuperAdmin);

// GET /api/admin/logs
router.get('/', async (req, res) => {
    try {
        const page    = Math.max(1, parseInt(req.query.page   || '1'));
        const limit   = Math.min(100, parseInt(req.query.limit || '50'));
        const offset  = (page - 1) * limit;
        const search  = req.query.search  || '';
        const action  = req.query.action  || '';
        const module  = req.query.module  || '';
        const status  = req.query.status  || '';
        const dateFrom= req.query.dateFrom|| '';
        const dateTo  = req.query.dateTo  || '';
        const sort    = req.query.sort === 'asc' ? 'ASC' : 'DESC';

        let where = ['1=1'], params = [];

        if (search) {
            where.push('(l.admin_email LIKE ? OR l.action LIKE ?)');
            params.push(`%${search}%`, `%${search}%`);
        }
        if (action) { where.push('l.action = ?'); params.push(action); }
        if (module) { where.push('l.module = ?'); params.push(module); }
        if (status === 'SUCCESS' || status === 'FAILURE') {
            where.push('l.status = ?'); params.push(status);
        }
        if (dateFrom) { where.push('DATE(l.created_at) >= ?'); params.push(dateFrom); }
        if (dateTo)   { where.push('DATE(l.created_at) <= ?'); params.push(dateTo); }

        const [[{ total }]] = await db.query(
            `SELECT COUNT(*) as total FROM admin_access_logs l WHERE ${where.join(' AND ')}`, params
        );

        const [rows] = await db.query(`
            SELECT l.*, a.name as admin_name
            FROM admin_access_logs l
            LEFT JOIN admins a ON a.id = l.admin_id
            WHERE ${where.join(' AND ')}
            ORDER BY l.created_at ${sort}
            LIMIT ? OFFSET ?
        `, [...params, limit, offset]);

        res.json({ logs: rows, total, page, limit, pages: Math.ceil(total / limit) });
    } catch (err) {
        res.status(500).json({ error: 'Failed to load access logs' });
    }
});

// GET /api/admin/logs/actions — distinct action values for filter dropdown
router.get('/actions', async (req, res) => {
    try {
        const [rows] = await db.query('SELECT DISTINCT action FROM admin_access_logs ORDER BY action');
        res.json(rows.map(r => r.action));
    } catch (err) {
        res.status(500).json({ error: 'Failed to load actions' });
    }
});

module.exports = router;
