const fs = require('fs');
const path = require('path');

const PRODUCTS_FILE = path.join(__dirname, '..', 'data', 'products.json');
const IMAGES_DIR = path.join(__dirname, '..', 'images');

// Helper to read products
function readProducts() {
    try {
        const data = fs.readFileSync(PRODUCTS_FILE, 'utf8');
        return JSON.parse(data);
    } catch (err) {
        console.error("Error reading products:", err);
        return [];
    }
}

// Helper to write products
function writeProducts(products) {
    fs.writeFileSync(PRODUCTS_FILE, JSON.stringify(products, null, 2), 'utf8');
}

module.exports = async function handler(req, res) {
    // Set CORS headers
    res.setHeader('Access-Control-Allow-Credentials', true);
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET,POST,DELETE,OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'X-CSRF-Token, X-Requested-With, Accept, Accept-Version, Content-Length, Content-MD5, Content-Type, Date, X-Api-Version');

    if (req.method === 'OPTIONS') {
        res.writeHead(200);
        res.end();
        return;
    }

    if (req.method === 'GET') {
        const products = readProducts();
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(products));
        return;
    }

    if (req.method === 'POST') {
        let body = '';
        req.on('data', chunk => {
            body += chunk.toString();
        });
        req.on('end', () => {
            try {
                const newProduct = JSON.parse(body);
                
                // Handle Base64 image saving
                if (newProduct.image && newProduct.image.startsWith('data:image')) {
                    const matches = newProduct.image.match(/^data:image\/([A-Za-z-+\/]+);base64,(.+)$/);
                    if (matches && matches.length === 3) {
                        const extension = matches[1];
                        const base64Data = matches[2];
                        const buffer = Buffer.from(base64Data, 'base64');
                        const filename = `product_${Date.now()}.${extension}`;
                        const filepath = path.join(IMAGES_DIR, filename);
                        fs.writeFileSync(filepath, buffer);
                        newProduct.image = `images/${filename}`;
                    }
                }

                newProduct.id = `prod_${Date.now()}`;
                
                const products = readProducts();
                products.push(newProduct);
                writeProducts(products);

                res.writeHead(201, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify(newProduct));
            } catch (err) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Invalid data' }));
            }
        });
        return;
    }
    
    if (req.method === 'DELETE') {
        // Parse ID from URL query or path if needed, but for simplicity we can pass it in body or query.
        // Assuming path is like /api/products?id=prod_xxx
        const parsedUrl = new URL(req.url, `http://${req.headers.host}`);
        const id = parsedUrl.searchParams.get('id');
        
        if (id) {
            let products = readProducts();
            products = products.filter(p => p.id !== id);
            writeProducts(products);
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ success: true }));
        } else {
            res.writeHead(400, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'Missing product id' }));
        }
        return;
    }

    res.writeHead(405, { 'Content-Type': 'text/plain' });
    res.end('Method Not Allowed');
};
