// server.js — THE 22KT GOLD | Express + MySQL Backend
// Replaces the original http-module server with a full Express application

require('dotenv').config();

const express = require('express');
const cors    = require('cors');
const path    = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// ── Middleware ──
app.use(cors({ origin: true, credentials: true }));
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// ── Static files ──
// On Vercel, use process.cwd() which points to the project root
const ROOT = process.env.VERCEL ? process.cwd() : __dirname;
app.use(express.static(ROOT));
app.use('/uploads', express.static(path.join(ROOT, 'uploads')));

// Explicit root route
app.get('/', (req, res) => {
    res.sendFile(path.join(ROOT, 'index.html'));
});

// ── API Routes ──
app.use('/api/admin/auth',         require('./backend/routes/auth.routes'));
app.use('/api/admin/dashboard',    require('./backend/routes/dashboard.routes'));
app.use('/api/admin/orders',       require('./backend/routes/orders.routes'));
app.use('/api/admin/users',        require('./backend/routes/users.routes'));
app.use('/api/admin/products',     require('./backend/routes/products.routes'));
app.use('/api/admin/categories',   require('./backend/routes/categories.routes'));
app.use('/api/admin/gallery',      require('./backend/routes/gallery.routes'));
app.use('/api/admin/gold-rates',   require('./backend/routes/gold-rates.routes'));
app.use('/api/admin/enquiries',    require('./backend/routes/enquiries.routes'));
app.use('/api/admin/custom-orders',require('./backend/routes/custom-orders.routes'));
app.use('/api/admin/admins',       require('./backend/routes/admins.routes'));
app.use('/api/admin/settings',     require('./backend/routes/settings.routes'));
app.use('/api/admin/logs',         require('./backend/routes/logs.routes'));

// ── Legacy gold-rates endpoint (public-facing pages still use /api/gold-rates) ──
const legacyGoldHandler = require('./api/gold-rates');
app.get('/api/gold-rates', (req, res) => legacyGoldHandler(req, res));

// ── 404 for unknown API routes ──
app.use('/api', (req, res) => res.status(404).json({ error: 'API endpoint not found' }));

// ── Global error handler ──
app.use((err, req, res, next) => {
    if (err.code === 'LIMIT_FILE_SIZE') {
        return res.status(400).json({ error: 'File too large. Maximum allowed size is 8 MB.' });
    }
    console.error('Unhandled error:', err);
    res.status(500).json({ error: err.message || 'Internal server error' });
});

// ── Start (Only if not in Vercel environment) ──
if (process.env.NODE_ENV !== 'production' && !process.env.VERCEL) {
    app.listen(PORT, () => {
        console.log(`\n👑 THE 22KT GOLD Server running at http://localhost:${PORT}`);
        console.log(`📡 Admin API:     http://localhost:${PORT}/api/admin/`);
        console.log(`💛 Gold Rate API: http://localhost:${PORT}/api/gold-rates\n`);
    });
}

// ── Export for Vercel Serverless Functions ──
module.exports = app;
