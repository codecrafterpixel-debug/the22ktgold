// backend/routes/auth.routes.js — Login / Logout / Me

const express  = require('express');
const bcrypt   = require('bcryptjs');
const db       = require('../db');
const { signToken, requireAuth, logAction } = require('../auth');

const router = express.Router();

// POST /api/admin/login
router.post('/login', async (req, res) => {
    const { email, password } = req.body;
    if (!email || !password) {
        return res.status(400).json({ error: 'Email and password are required' });
    }

    try {
        const [rows] = await db.query(
            'SELECT * FROM admins WHERE email = ? LIMIT 1',
            [email.toLowerCase().trim()]
        );

        if (!rows.length) {
            await logAction(null, email, 'LOGIN', 'Auth', req, 'FAILURE', 'Admin not found');
            return res.status(401).json({ error: 'Invalid credentials' });
        }

        const admin = rows[0];

        if (admin.status === 'DISABLED') {
            await logAction(admin.id, admin.email, 'LOGIN', 'Auth', req, 'FAILURE', 'Account disabled');
            return res.status(401).json({ error: 'Your account has been disabled. Contact Super Admin.' });
        }

        const valid = await bcrypt.compare(password, admin.password_hash);
        if (!valid) {
            await logAction(admin.id, admin.email, 'LOGIN', 'Auth', req, 'FAILURE', 'Wrong password');
            return res.status(401).json({ error: 'Invalid credentials' });
        }

        // Update last_login
        await db.query('UPDATE admins SET last_login = NOW() WHERE id = ?', [admin.id]);

        const token = signToken(admin);
        await logAction(admin.id, admin.email, 'LOGIN', 'Auth', req, 'SUCCESS');

        res.json({
            token,
            admin: {
                id:    admin.id,
                name:  admin.name,
                email: admin.email,
                role:  admin.role
            }
        });
    } catch (err) {
        console.error('Login error:', err);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// POST /api/admin/logout
router.post('/logout', requireAuth, async (req, res) => {
    await logAction(req.admin.id, req.admin.email, 'LOGOUT', 'Auth', req);
    res.json({ success: true });
});

// GET /api/admin/me — verify token + return admin info
router.get('/me', requireAuth, (req, res) => {
    res.json({
        id:    req.admin.id,
        name:  req.admin.name,
        email: req.admin.email,
        role:  req.admin.role
    });
});

module.exports = router;
