// backend/routes/gold-rates.routes.js — Gold rates with DB history + manual override

const express = require('express');
const db      = require('../db');
const { requireAuth, requireSuperAdmin, logAction } = require('../auth');

const router = express.Router();

// Cache from original api/gold-rates.js logic
let cachedApiData = null;
let lastApiFetch  = 0;
const CACHE_TTL   = 60 * 1000;

async function fetchLiveGoldRates() {
    const now    = Date.now();
    if (cachedApiData && (now - lastApiFetch) < CACHE_TTL) return cachedApiData;

    const apiKey = process.env.GOLD_API_KEY;
    let rate24k  = 0, prevClose24k = 0, change24k = 0, changePercent = 0, provider = 'Indicative';

    if (apiKey) {
        try {
            const ctrl    = new AbortController();
            const timeout = setTimeout(() => ctrl.abort(), 5000);
            const res     = await fetch('https://www.goldapi.io/api/XAU/INR', {
                signal: ctrl.signal,
                headers: { 'x-access-token': apiKey, 'Content-Type': 'application/json' }
            });
            clearTimeout(timeout);
            if (res.ok) {
                const data   = await res.json();
                rate24k      = data.price_gram_24k || (data.price / 31.1034768);
                prevClose24k = data.prev_close_price ? (data.prev_close_price / 31.1034768) : rate24k;
                change24k    = data.ch ? (data.ch / 31.1034768) : (rate24k - prevClose24k);
                changePercent= data.chp || (prevClose24k > 0 ? (change24k / prevClose24k) * 100 : 0);
                provider     = 'GoldAPI.io (Live XAU/INR)';
            }
        } catch {}
    }

    if (!rate24k) {
        try {
            const ctrl = new AbortController();
            const timeout = setTimeout(() => ctrl.abort(), 5000);
            const res  = await fetch(
                'https://api.coingecko.com/api/v3/simple/price?ids=pax-gold&vs_currencies=inr&include_24hr_change=true',
                { signal: ctrl.signal }
            );
            clearTimeout(timeout);
            if (res.ok) {
                const data  = await res.json();
                rate24k     = data['pax-gold'].inr / 31.1034768;
                changePercent= data['pax-gold'].inr_24h_change || 0;
                change24k   = rate24k * (changePercent / 100);
                provider    = 'Spot Bullion Feed';
            }
        } catch {}
    }

    if (!rate24k) {
        rate24k       = 7350;
        change24k     = 0;
        changePercent = 0;
        provider      = 'Market Indicative Rate';
    }

    const rate22k   = rate24k * (22 / 24);
    const rate18k   = rate24k * (18 / 24);
    const change22k = change24k * (22 / 24);

    cachedApiData = { rate24k, rate22k, rate18k, change24k, change22k, changePercent, provider, fetchedAt: new Date().toISOString() };
    lastApiFetch  = now;
    return cachedApiData;
}

// GET /api/admin/gold-rates
router.get('/', requireAuth, async (req, res) => {
    try {
        // Check for manual override
        const [settings] = await db.query(
            `SELECT setting_key, setting_value FROM site_settings WHERE setting_key IN ('gold_is_manual','gold_manual_22k','gold_manual_24k')`
        );
        const settingMap = {};
        settings.forEach(s => { settingMap[s.setting_key] = s.setting_value; });

        const live = await fetchLiveGoldRates();
        let finalRates;

        if (settingMap['gold_is_manual'] === '1' && settingMap['gold_manual_22k']) {
            const m22k = parseFloat(settingMap['gold_manual_22k']);
            const m24k = parseFloat(settingMap['gold_manual_24k'] || m22k * (24/22));
            finalRates = {
                isManual:       true,
                provider:       'Manual Admin Rate',
                rate22k:        m22k,
                rate24k:        m24k,
                rate18k:        m24k * (18/24),
                change:         0,
                changePercent:  0,
                fetchedAt:      new Date().toISOString()
            };
        } else {
            finalRates = {
                isManual:       false,
                provider:       live.provider,
                rate22k:        +live.rate22k.toFixed(2),
                rate24k:        +live.rate24k.toFixed(2),
                rate18k:        +live.rate18k.toFixed(2),
                change:         +live.change22k.toFixed(2),
                changePercent:  +live.changePercent.toFixed(3),
                fetchedAt:      live.fetchedAt
            };
        }

        res.json(finalRates);
    } catch (err) {
        console.error('Gold rates error:', err);
        res.status(500).json({ error: 'Failed to fetch gold rates' });
    }
});

// POST /api/admin/gold-rates/refresh — force refresh + save to history
router.post('/refresh', requireAuth, async (req, res) => {
    cachedApiData = null;
    lastApiFetch  = 0;
    try {
        const live = await fetchLiveGoldRates();

        // Save to gold_rate_history
        await db.query(
            `INSERT INTO gold_rate_history (rate_22k, rate_24k, rate_18k, change_amount, change_percent, source)
             VALUES (?,?,?,?,?,?)`,
            [
                +live.rate22k.toFixed(2), +live.rate24k.toFixed(2), +live.rate18k.toFixed(2),
                +live.change22k.toFixed(2), +live.changePercent.toFixed(3), live.provider
            ]
        );

        await logAction(req.admin.id, req.admin.email, 'REFRESH_GOLD_RATE', 'Gold Rates', req);
        res.json({ success: true, ...live });
    } catch (err) {
        res.status(500).json({ error: 'Failed to refresh rates' });
    }
});

// GET /api/admin/gold-rates/history
router.get('/history', requireAuth, async (req, res) => {
    try {
        const limit = Math.min(100, parseInt(req.query.limit || '30'));
        const [rows] = await db.query(
            'SELECT * FROM gold_rate_history ORDER BY created_at DESC LIMIT ?',
            [limit]
        );
        res.json(rows);
    } catch (err) {
        res.status(500).json({ error: 'Failed to load gold rate history' });
    }
});

// PATCH /api/admin/gold-rates/override — Super Admin: set manual override
router.patch('/override', requireAuth, requireSuperAdmin, async (req, res) => {
    const { is_manual, manual_22k, manual_24k } = req.body;
    try {
        const upsert = async (key, value) => {
            await db.query(
                `INSERT INTO site_settings (setting_key, setting_value, updated_by) VALUES (?,?,?)
                 ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value), updated_by=VALUES(updated_by), updated_at=NOW()`,
                [key, value, req.admin.id]
            );
        };
        await upsert('gold_is_manual', is_manual ? '1' : '0');
        if (manual_22k) await upsert('gold_manual_22k', manual_22k);
        if (manual_24k) await upsert('gold_manual_24k', manual_24k);
        await logAction(req.admin.id, req.admin.email, 'UPDATE_GOLD_RATE_SETTINGS', 'Gold Rates', req);
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: 'Failed to update override settings' });
    }
});

module.exports = router;
