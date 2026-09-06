// backend/routes/admins.routes.js — Admin account management (SUPER ADMIN ONLY)

const express = require('express');
const bcrypt  = require('bcryptjs');
const db      = require('../db');
const { requireAuth, requireSuperAdmin, logAction } = require('../auth');

const router = express.Router();

// All routes require auth + super admin
router.use(requireAuth, requireSuperAdmin);

// GET /api/admin/admins
router.get('/', async (req, res) => {
    try {
        const [rows] = await db.query(
            `SELECT id, name, email, role, status, last_login, created_at, updated_at
             FROM admins ORDER BY created_at ASC`
        );
        res.json(rows);
    } catch (err) {
        res.status(500).json({ error: 'Failed to load admins' });
    }
});

// GET /api/admin/admins/:id
router.get('/:id', async (req, res) => {
    try {
        const [rows] = await db.query(
            `SELECT id, name, email, role, status, last_login, created_at, updated_at
             FROM admins WHERE id = ?`,
            [req.params.id]
        );
        if (!rows.length) return res.status(404).json({ error: 'Admin not found' });
        res.json(rows[0]);
    } catch (err) {
        res.status(500).json({ error: 'Failed to load admin' });
    }
});

// POST /api/admin/admins — create admin
router.post('/', async (req, res) => {
    const { name, email, password, confirm_password, role, status } = req.body;

    if (!name || !name.trim())      return res.status(400).json({ error: 'Name is required' });
    if (!email || !email.trim())    return res.status(400).json({ error: 'Email is required' });
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return res.status(400).json({ error: 'Invalid email format' });
    if (!password)                  return res.status(400).json({ error: 'Password is required' });
    if (password.length < 8)        return res.status(400).json({ error: 'Password must be at least 8 characters' });
    if (password !== confirm_password) return res.status(400).json({ error: 'Passwords do not match' });
    if (!['ADMIN','SUPER_ADMIN'].includes(role)) return res.status(400).json({ error: 'Invalid role' });

    try {
        const [exists] = await db.query('SELECT id FROM admins WHERE email = ?', [email.toLowerCase()]);
        if (exists.length) return res.status(400).json({ error: 'An admin with this email already exists' });

        const hash = await bcrypt.hash(password, 12);
        const [result] = await db.query(
            'INSERT INTO admins (name, email, password_hash, role, status) VALUES (?,?,?,?,?)',
            [name.trim(), email.toLowerCase(), hash, role || 'ADMIN', status || 'ACTIVE']
        );

        await logAction(req.admin.id, req.admin.email, 'CREATE_ADMIN', 'Admin Accounts', req, 'SUCCESS',
            `Created ${role} account for ${email}`);

        const [admin] = await db.query(
            'SELECT id, name, email, role, status, created_at FROM admins WHERE id = ?',
            [result.insertId]
        );
        res.status(201).json(admin[0]);
    } catch (err) {
        console.error('Create admin error:', err);
        res.status(500).json({ error: 'Failed to create admin' });
    }
});

// PUT /api/admin/admins/:id — edit admin (not password)
router.put('/:id', async (req, res) => {
    const { name, email, role, status } = req.body;

    if (!name || !name.trim()) return res.status(400).json({ error: 'Name is required' });
    if (!email || !email.trim()) return res.status(400).json({ error: 'Email is required' });
    if (!['ADMIN','SUPER_ADMIN'].includes(role)) return res.status(400).json({ error: 'Invalid role' });
    if (!['ACTIVE','DISABLED'].includes(status)) return res.status(400).json({ error: 'Invalid status' });

    const targetId = parseInt(req.params.id);

    try {
        const [check] = await db.query('SELECT * FROM admins WHERE id = ?', [targetId]);
        if (!check.length) return res.status(404).json({ error: 'Admin not found' });

        // Prevent removing last Super Admin
        if ((role === 'ADMIN' || status === 'DISABLED') && check[0].role === 'SUPER_ADMIN') {
            const [[{ cnt }]] = await db.query(
                `SELECT COUNT(*) as cnt FROM admins WHERE role = 'SUPER_ADMIN' AND status = 'ACTIVE'`
            );
            if (cnt <= 1) {
                return res.status(400).json({ error: 'At least one active Super Admin account is required.' });
            }
        }

        const [emailExists] = await db.query('SELECT id FROM admins WHERE email = ? AND id != ?', [email.toLowerCase(), targetId]);
        if (emailExists.length) return res.status(400).json({ error: 'Email already in use' });

        await db.query(
            'UPDATE admins SET name=?, email=?, role=?, status=?, updated_at=NOW() WHERE id=?',
            [name.trim(), email.toLowerCase(), role, status, targetId]
        );

        await logAction(req.admin.id, req.admin.email, 'UPDATE_ADMIN', 'Admin Accounts', req, 'SUCCESS',
            `Updated admin ${email}`);

        const [updated] = await db.query(
            'SELECT id, name, email, role, status, last_login, created_at, updated_at FROM admins WHERE id = ?',
            [targetId]
        );
        res.json(updated[0]);
    } catch (err) {
        res.status(500).json({ error: 'Failed to update admin' });
    }
});

// PATCH /api/admin/admins/:id/status — enable/disable
router.patch('/:id/status', async (req, res) => {
    const { status } = req.body;
    if (!['ACTIVE','DISABLED'].includes(status)) {
        return res.status(400).json({ error: 'Invalid status' });
    }
    const targetId = parseInt(req.params.id);

    try {
        const [check] = await db.query('SELECT * FROM admins WHERE id = ?', [targetId]);
        if (!check.length) return res.status(404).json({ error: 'Admin not found' });

        // Prevent disabling the last active Super Admin
        if (status === 'DISABLED' && check[0].role === 'SUPER_ADMIN') {
            const [[{ cnt }]] = await db.query(
                `SELECT COUNT(*) as cnt FROM admins WHERE role = 'SUPER_ADMIN' AND status = 'ACTIVE'`
            );
            if (cnt <= 1) {
                return res.status(400).json({ error: 'At least one active Super Admin account is required.' });
            }
        }

        await db.query('UPDATE admins SET status = ?, updated_at = NOW() WHERE id = ?', [status, targetId]);
        const action = status === 'ACTIVE' ? 'ENABLE_ADMIN' : 'DISABLE_ADMIN';
        await logAction(req.admin.id, req.admin.email, action, 'Admin Accounts', req, 'SUCCESS',
            `${action} for admin ID ${targetId}`);

        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: 'Failed to update admin status' });
    }
});

// POST /api/admin/admins/:id/reset-password
router.post('/:id/reset-password', async (req, res) => {
    const { new_password, confirm_password } = req.body;
    if (!new_password || new_password.length < 8) return res.status(400).json({ error: 'Password must be at least 8 characters' });
    if (new_password !== confirm_password) return res.status(400).json({ error: 'Passwords do not match' });

    try {
        const [check] = await db.query('SELECT id FROM admins WHERE id = ?', [req.params.id]);
        if (!check.length) return res.status(404).json({ error: 'Admin not found' });

        const hash = await bcrypt.hash(new_password, 12);
        await db.query('UPDATE admins SET password_hash = ?, updated_at = NOW() WHERE id = ?', [hash, req.params.id]);
        await logAction(req.admin.id, req.admin.email, 'RESET_ADMIN_PASSWORD', 'Admin Accounts', req);
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: 'Failed to reset password' });
    }
});

module.exports = router;
