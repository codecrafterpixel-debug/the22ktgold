require('dotenv').config();
const express = require('express');
const cors = require('cors');

const app = express();

app.use(cors({ origin: true, credentials: true }));
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// ── API Routes ──
app.use('/api/admin/auth',         require('../backend/routes/auth.routes'));
app.use('/api/admin/dashboard',    require('../backend/routes/dashboard.routes'));
app.use('/api/admin/orders',       require('../backend/routes/orders.routes'));
app.use('/api/admin/users',        require('../backend/routes/users.routes'));
app.use('/api/admin/products',     require('../backend/routes/products.routes'));
app.use('/api/admin/categories',   require('../backend/routes/categories.routes'));
app.use('/api/admin/gallery',      require('../backend/routes/gallery.routes'));
app.use('/api/admin/gold-rates',   require('../backend/routes/gold-rates.routes'));
app.use('/api/admin/enquiries',    require('../backend/routes/enquiries.routes'));
app.use('/api/admin/custom-orders',require('../backend/routes/custom-orders.routes'));
app.use('/api/admin/admins',       require('../backend/routes/admins.routes'));
app.use('/api/admin/settings',     require('../backend/routes/settings.routes'));
app.use('/api/admin/logs',         require('../backend/routes/logs.routes'));

// ── Legacy gold-rates endpoint ──
const legacyGoldHandler = require('./gold-rates');
app.get('/api/gold-rates', (req, res) => legacyGoldHandler(req, res));

app.use('/api', (req, res) => res.status(404).json({ error: 'API endpoint not found' }));

app.use((err, req, res, next) => {
    console.error('Unhandled error:', err);
    res.status(500).json({ error: err.message || 'Internal server error' });
});

module.exports = app;
