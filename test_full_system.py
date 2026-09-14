import sys, json
sys.path.insert(0, 'backend')
import server

def run_tests():
    server.init_db()
    client = server.app.test_client()

    print("--- 1. Testing Admin Authentication ---")
    login_res = client.post('/api/admin/auth/login', json={'email': '22ktgold@yashpanchal.com', 'password': 'Yash2112'})
    assert login_res.status_code == 200, f"Login failed: {login_res.data}"
    token = login_res.get_json()['token']
    headers = {'Authorization': f'Bearer {token}'}
    print("[PASS] Super Admin login successful")

    print("\n--- 2. Testing Public Endpoints ---")
    res_cats = client.get('/api/categories')
    assert res_cats.status_code == 200
    cats = res_cats.get_json()
    assert len(cats) > 0
    print(f"[PASS] /api/categories returned {len(cats)} categories")

    res_prods = client.get('/api/products')
    assert res_prods.status_code == 200
    prods_data = res_prods.get_json()
    prods = prods_data if isinstance(prods_data, list) else prods_data.get('products', [])
    assert len(prods) > 0
    print(f"[PASS] /api/products returned {len(prods)} products")

    res_rates = client.get('/api/gold-rates')
    assert res_rates.status_code == 200
    rates = res_rates.get_json()
    assert 'gold' in rates and '22k' in rates['gold']
    print(f"[PASS] /api/gold-rates returned live 22KT rate: INR {rates['gold']['22k']['perGram']:.2f}")

    res_gallery = client.get('/api/gallery')
    assert res_gallery.status_code == 200
    gallery_items = res_gallery.get_json()
    print(f"[PASS] /api/gallery returned {len(gallery_items)} items")

    print("\n--- 3. Testing Storefront Order Placement & Auto-Customer Creation ---")
    order_data = {
        'customer_name': 'Test Buyer',
        'customer_email': 'testbuyer@example.com',
        'customer_phone': '+91 99999 88888',
        'customer_address': '123 Test Street, Ahmedabad',
        'product_id': 1,
        'product_name': '22KT Royal Peacock Gold Necklace',
        'purity': '22KT',
        'weight': 34.5,
        'total_amount': 250000,
        'payment_method': 'Online / UPI Advance',
        'notes': 'Urgent booking'
    }
    res_order = client.post('/api/orders', json=order_data)
    assert res_order.status_code == 201, f"Order creation failed: {res_order.data}"
    order_id = res_order.get_json()['order_id']
    print(f"[PASS] /api/orders created order #{order_id}")

    print("\n--- 4. Testing Storefront Contact Enquiry Submission ---")
    enq_data = {
        'name': 'Test Inquirer',
        'email': 'inquiry@example.com',
        'phone': '+91 98888 77777',
        'subject': 'Bridal Gold Inquiry',
        'message': 'Need pricing for full bridal set',
        'source': 'Contact Page'
    }
    res_enq = client.post('/api/enquiries', json=enq_data)
    assert res_enq.status_code == 201
    print("[PASS] /api/enquiries stored enquiry")

    print("\n--- 5. Testing Storefront Bespoke Custom Order Submission ---")
    cust_data = {
        'name': 'Bespoke Customer',
        'email': 'bespoke@example.com',
        'phone': '+91 97777 66666',
        'address': 'Bespoke Studio, Surat',
        'jewellery_type': 'Gold Necklace',
        'occasion': 'Wedding',
        'purity': '22 KT',
        'weight': '45 grams',
        'size': 'Standard',
        'finish': 'Antique',
        'budget': '350000',
        'description': 'Handcrafted antique floral choker',
        'reference_link': 'https://instagram.com/sample'
    }
    res_cust = client.post('/api/custom-orders', json=cust_data)
    assert res_cust.status_code == 201
    print("[PASS] /api/custom-orders stored custom order")

    print("\n--- 6. Testing Dynamic Product Addition in Admin Panel ---")
    new_prod_data = {
        'name': 'Dynamic Kundan Heritage Choker',
        'category_id': 2,
        'description': 'Exquisite 22KT handcrafted kundan choker',
        'purity': 22,
        'weight': 52.0,
        'making_charges': 1800,
        'current_price': 385000,
        'stock': 2,
        'sku': 'CHK-22K-999',
        'featured': 'true',
        'active': 'true'
    }
    res_add_prod = client.post('/api/admin/products', data=new_prod_data, headers=headers)
    assert res_add_prod.status_code == 201, f"Admin product add failed: {res_add_prod.data}"
    added_prod_id = res_add_prod.get_json()['id']
    print(f"[PASS] /api/admin/products created product #{added_prod_id}")

    # Immediately check public /api/products
    res_pub_prods = client.get('/api/products')
    pub_data = res_pub_prods.get_json()
    pub_prods = pub_data if isinstance(pub_data, list) else pub_data.get('products', [])
    found = any(p['id'] == added_prod_id for p in pub_prods)
    assert found, "Product added in Admin Panel was NOT returned in public collections list!"
    print(f"[PASS] Verified product #{added_prod_id} appears directly on collections page (/api/products)")

    print("\n--- 7. Testing Admin Dashboard Aggregates ---")
    res_dash = client.get('/api/admin/dashboard', headers=headers)
    assert res_dash.status_code == 200
    dash_stats = res_dash.get_json()
    print(f"[PASS] Dashboard stats -> Orders: {dash_stats['total_orders']}, Users: {dash_stats['total_users']}, Products: {dash_stats['total_products']}, Revenue: INR {dash_stats['total_revenue']}")

    print("\n--- 8. Testing Admin Module Lists ---")
    res_adm_orders = client.get('/api/admin/orders', headers=headers)
    assert res_adm_orders.status_code == 200 and len(res_adm_orders.get_json()['orders']) >= 1
    print(f"[PASS] Admin Orders -> {len(res_adm_orders.get_json()['orders'])} orders found")

    res_adm_cust = client.get('/api/admin/custom-orders', headers=headers)
    assert res_adm_cust.status_code == 200 and len(res_adm_cust.get_json()['requests']) >= 1
    print(f"[PASS] Admin Custom Orders -> {len(res_adm_cust.get_json()['requests'])} requests found")

    res_adm_enq = client.get('/api/admin/enquiries', headers=headers)
    assert res_adm_enq.status_code == 200 and len(res_adm_enq.get_json()['enquiries']) >= 1
    print(f"[PASS] Admin Enquiries -> {len(res_adm_enq.get_json()['enquiries'])} enquiries found")

    res_adm_users = client.get('/api/admin/users', headers=headers)
    assert res_adm_users.status_code == 200 and len(res_adm_users.get_json()['users']) >= 3
    print(f"[PASS] Admin Users (auto-registered customers) -> {len(res_adm_users.get_json()['users'])} users found")

    print("\n=======================================================")
    print("ALL MODULES & DYNAMIC WORKFLOWS VERIFIED SUCCESSFULLY!")
    print("=======================================================")

if __name__ == '__main__':
    run_tests()
