// backend/auth.js — JWT middleware + RBAC helpers

require('dotenv').config();
const jwt  = require('jsonwebtoken');
const db   = require('./db');

const SECRET = process.env.JWT_SECRET || 'fallback_dev_secret_change_in_prod';

/**
 * Sign a JWT token for an admin
 */
function signToken(admin) {
    return jwt.sign(
        {
            id:     admin.id,
            email:  admin.email,
            role:   admin.role,
            name:   admin.name
        },
        SECRET,
        { expiresIn: process.env.JWT_EXPIRES_IN || '8h' }
    );
}

/**
 * Express middleware: validates JWT from Authorization header
 * Sets req.admin = decoded payload
 */
async function requireAuth(req, res, next) {
    const header = req.headers.authorization;
    if (!header || !header.startsWith('Bearer ')) {
        return res.status(401).json({ error: 'Unauthorized — no token provided' });
    }
    const token = header.slice(7);
    try {
        const decoded = jwt.verify(token, SECRET);
        // Verify account is still active in DB (catches disabled accounts)
        const [rows] = await db.query(
            'SELECT id, name, email, role, status FROM admins WHERE id = ?',
            [decoded.id]
        );
        if (!rows.length || rows[0].status === 'DISABLED') {
            return res.status(401).json({ error: 'Account is disabled or not found' });
        }
        req.admin = rows[0];
        next();
    } catch (err) {
        return res.status(401).json({ error: 'Invalid or expired token' });
    }
}

/**
 * Express middleware: only Super Admins may proceed
 */
function requireSuperAdmin(req, res, next) {
    if (!req.admin || req.admin.role !== 'SUPER_ADMIN') {
        return res.status(403).json({ error: 'Forbidden — Super Admin access required' });
    }
    next();
}

/**
 * Log an admin action to admin_access_logs
 */
async function logAction(adminId, adminEmail, action, module, req, status = 'SUCCESS', notes = null) {
    try {
        const ip  = req.headers['x-forwarded-for'] || req.socket?.remoteAddress || null;
        const ua  = req.headers['user-agent'] || null;
        await db.query(
            `INSERT INTO admin_access_logs (admin_id, admin_email, action, module, ip_address, user_agent, status, notes)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
            [adminId || null, adminEmail || null, action, module, ip, ua, status, notes]
        );
    } catch (e) {
        // Never crash the app because of a logging error
        console.warn('Access log write failed:', e.message);
    }
}

module.exports = { signToken, requireAuth, requireSuperAdmin, logAction };
