// backend/routes/dashboard.routes.js — Dashboard statistics

const express = require('express');
const db      = require('../db');
const { requireAuth } = require('../auth');

const router = express.Router();

// GET /api/admin/dashboard
router.get('/', requireAuth, async (req, res) => {
    try {
        const [[orderStats]]   = await db.query(`SELECT COUNT(*) as total FROM orders`);
        const [[userStats]]    = await db.query(`SELECT COUNT(*) as total FROM users WHERE status = 'ACTIVE'`);
        const [[customStats]]  = await db.query(`SELECT COUNT(*) as total FROM custom_orders WHERE status NOT IN ('Completed','Rejected')`);
        const [[enquiryStats]] = await db.query(`SELECT COUNT(*) as total FROM enquiries WHERE status IN ('New','In Progress','Contacted')`);

        // Recent orders (last 10)
        const [recentOrders] = await db.query(`
            SELECT id, order_number, customer_name, product_name, weight, order_status, payment_status, created_at
            FROM orders
            ORDER BY created_at DESC
            LIMIT 10
        `);

        res.json({
            stats: {
                totalOrders:    orderStats.total,
                registeredUsers: userStats.total,
                customRequests: customStats.total,
                openEnquiries:  enquiryStats.total
            },
            recentOrders
        });
    } catch (err) {
        console.error('Dashboard error:', err);
        res.status(500).json({ error: 'Failed to load dashboard data' });
    }
});

module.exports = router;
