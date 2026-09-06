// backend/routes/settings.routes.js — Site settings (SUPER ADMIN ONLY)

const express = require('express');
const db      = require('../db');
const { requireAuth, requireSuperAdmin, logAction } = require('../auth');

const router = express.Router();

router.use(requireAuth, requireSuperAdmin);

// GET /api/admin/settings
router.get('/', async (req, res) => {
    try {
        const [rows] = await db.query('SELECT setting_key, setting_value FROM site_settings ORDER BY setting_key');
        const settings = {};
        rows.forEach(r => { settings[r.setting_key] = r.setting_value; });
        res.json(settings);
    } catch (err) {
        res.status(500).json({ error: 'Failed to load settings' });
    }
});

// PUT /api/admin/settings — bulk update
router.put('/', async (req, res) => {
    const updates = req.body; // { key: value, ... }
    if (!updates || typeof updates !== 'object') {
        return res.status(400).json({ error: 'Invalid settings payload' });
    }

    const ALLOWED_KEYS = [
        'business_name','business_email','business_phone','business_whatsapp','business_address','business_hours',
        'website_title','meta_description','default_currency','default_country','timezone',
        'contact_email','support_phone','instagram','facebook','youtube','google_business',
        'footer_text','copyright_text'
    ];

    const filteredKeys = Object.keys(updates).filter(k => ALLOWED_KEYS.includes(k));
    if (!filteredKeys.length) return res.status(400).json({ error: 'No valid settings keys provided' });

    try {
        for (const key of filteredKeys) {
            await db.query(
                `INSERT INTO site_settings (setting_key, setting_value, updated_by)
                 VALUES (?,?,?)
                 ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value), updated_by=VALUES(updated_by), updated_at=NOW()`,
                [key, updates[key], req.admin.id]
            );
        }
        await logAction(req.admin.id, req.admin.email, 'UPDATE_SETTINGS', 'Site Settings', req);
        res.json({ success: true });
    } catch (err) {
        console.error('Settings update error:', err);
        res.status(500).json({ error: 'Failed to update settings' });
    }
});

module.exports = router;
