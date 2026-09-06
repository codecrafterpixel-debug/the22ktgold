// backend/db.js — Local SQLite Database Connection & Query Wrapper
// Connects directly to the22ktgold.db with zero external DB dependencies

const sqlite3 = require('sqlite3').verbose();
const path    = require('path');
const fs      = require('fs');

const DB_PATH = path.join(__dirname, '..', 'the22ktgold.db');

const db = new sqlite3.Database(DB_PATH, (err) => {
    if (err) {
        console.error('❌ SQLite connection failed:', err.message);
    } else {
        console.log('✅ Connected to local SQLite database:', DB_PATH);
        db.run('PRAGMA foreign_keys = ON');
    }
});

/**
 * Universal query runner: executes SQL queries and returns [rows] or [{ insertId, affectedRows }]
 */
function query(sql, params = []) {
    return new Promise((resolve, reject) => {
        let cleanSql = sql.trim();

        // Convert Postgres/MySQL NOW() to datetime('now')
        cleanSql = cleanSql.replace(/\bNOW\(\)/gi, "datetime('now')");

        // Convert Postgres CURRENT_TIMESTAMP comparisons or boolean literals if needed
        cleanSql = cleanSql.replace(/\bTRUE\b/gi, '1').replace(/\bFALSE\b/gi, '0');

        // Check query type
        if (/^\s*(SELECT|PRAGMA)/i.test(cleanSql)) {
            db.all(cleanSql, params, (err, rows) => {
                if (err) {
                    console.error('SQLite SELECT Error:', err.message, '\nSQL:', cleanSql);
                    return reject(err);
                }
                resolve([rows || []]);
            });
        } else if (/^\s*INSERT/i.test(cleanSql)) {
            db.run(cleanSql, params, function (err) {
                if (err) {
                    console.error('SQLite INSERT Error:', err.message, '\nSQL:', cleanSql);
                    return reject(err);
                }
                const insertId = this.lastID;
                const affectedRows = this.changes;
                resolve([[{ insertId, affectedRows }], { insertId, affectedRows }]);
            });
        } else {
            // UPDATE, DELETE, CREATE, etc.
            db.run(cleanSql, params, function (err) {
                if (err) {
                    console.error('SQLite EXEC Error:', err.message, '\nSQL:', cleanSql);
                    return reject(err);
                }
                resolve([[{ insertId: null, affectedRows: this.changes }]]);
            });
        }
    });
}

module.exports = {
    query,
    db
};
