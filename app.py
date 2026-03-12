from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json
from collections import Counter

app = Flask(__name__)
app.secret_key = 'midnight_slice_secure_key'

# --- 1. CONFIGURATION & FORMULAS ---
# This is the "Standard Formula" you requested.
STANDARD_USAGE = {
    'Small':  {'dough': 150, 'sauce': 50,  'cheese': 80,  'topping_veg': 30, 'topping_meat': 40},
    'Medium': {'dough': 250, 'sauce': 80,  'cheese': 120, 'topping_veg': 50, 'topping_meat': 60},
    'Large':  {'dough': 400, 'sauce': 120, 'cheese': 200, 'topping_veg': 80, 'topping_meat': 100}
}

# --- 2. DATABASE SETUP ---
# --- 2. DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('pizza.db')
    c = conn.cursor()
    
    # Tables
    c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, password TEXT, role TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT, price REAL, category TEXT, image TEXT, description TEXT, type TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, user_id INTEGER, total_amount REAL, status TEXT, date TEXT, items_json TEXT, order_type TEXT, address TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS ingredients (id INTEGER PRIMARY KEY, name TEXT, quantity REAL, unit TEXT, threshold REAL DEFAULT 1000)''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory_logs (id INTEGER PRIMARY KEY, message TEXT, timestamp TEXT)''')
    
    # --- MIGRATION HACKS ---
    try:
        c.execute("SELECT address FROM orders LIMIT 1")
    except sqlite3.OperationalError:
        print("Migrating DB: Adding address column to orders...")
        c.execute("ALTER TABLE orders ADD COLUMN address TEXT")
        conn.commit()

    try:
        c.execute("SELECT email FROM users LIMIT 1")
    except sqlite3.OperationalError:
        print("Migrating DB: Adding email column to users...")
        c.execute("ALTER TABLE users ADD COLUMN email TEXT")
        conn.commit()
    # -----------------------------------------------------

    # Seed Admin (Updated to include email)
    c.execute("SELECT * FROM users WHERE username='admin'")
    if not c.fetchone():
        hashed_pw = generate_password_hash('admin')
        # Handle cases where the table was just created vs already existed
        try:
            c.execute("INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)", ('admin', 'admin@midnightslice.com', hashed_pw, 'admin'))
        except sqlite3.OperationalError:
            # Fallback if the migration hasn't fully committed in this transaction thread
            c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ('admin', hashed_pw, 'admin'))

    # Seed Ingredients (Expanded List)
    c.execute("SELECT count(*) FROM ingredients")
    if c.fetchone()[0] == 0:
        ingredients = [
            ('Pizza Dough', 50000, 'g'), ('Tomato Sauce', 20000, 'ml'), ('Mozzarella Cheese', 30000, 'g'),
            ('Pepperoni', 5000, 'g'), ('Chicken', 5000, 'g'), ('Bacon', 3000, 'g'),
            ('Onions', 5000, 'g'), ('Green Peppers', 5000, 'g'), ('Mushrooms', 5000, 'g'),
            ('Black Olives', 3000, 'g'), ('Sweet Corn', 3000, 'g'), ('Jalapenos', 3000, 'g'), ('Red Paprika', 3000, 'g')
        ]
        c.executemany("INSERT INTO ingredients (name, quantity, unit) VALUES (?, ?, ?)", ingredients)

    # Seed 16 Pizzas (Expanded Menu)
    c.execute("SELECT count(*) FROM products")
    if c.fetchone()[0] == 0:
        pizzas = [
            ('Margherita Classic', 299, 'Veg', 'San Marzano sauce, fresh mozzarella, basil.', 'Veg'),
            ('Double Cheese', 349, 'Veg', 'Loaded with extra mozzarella and liquid cheese.', 'Veg'),
            ('Farmhouse', 399, 'Veg', 'Onion, capsicum, tomato, mushroom.', 'Veg'),
            ('Peppy Paneer', 429, 'Veg', 'Spicy paneer cubes, capsicum, red paprika.', 'Veg'),
            ('Veggie Paradise', 449, 'Veg', 'Gold corn, black olives, capsicum, red paprika.', 'Veg'),
            ('Pepperoni Feast', 449, 'Non-Veg', 'Double pepperoni, extra mozzarella.', 'Non-Veg'),
            ('Chicken Dominator', 599, 'Non-Veg', 'Loaded with chicken tikka, sausage, salami.', 'Non-Veg'),
            ('Non-Veg Supreme', 549, 'Non-Veg', 'Chicken tikka, pepperoni, onion, mushroom.', 'Non-Veg'),
            ('Spicy Chicken', 479, 'Non-Veg', 'Red paprika, spicy chicken, hot sauce.', 'Non-Veg'),
            ('Chicken Golden Delight', 499, 'Non-Veg', 'Golden corn, double chicken, cheese.', 'Non-Veg'),
            ('Midnight Special', 699, 'Non-Veg', 'Chef’s special mix of meats and exotic veggies.', 'Non-Veg'),
            ('Tandoori Paneer', 459, 'Veg', 'Tandoori sauce base, paneer, onion, capsicum.', 'Veg'),
            ('Indi Tandoori Chicken', 529, 'Non-Veg', 'Tandoori sauce, chicken tikka, red onion.', 'Non-Veg'),
            ('Mexican Green Wave', 419, 'Veg', 'Crunchy onions, crisp capsicum, juicy tomatoes, jalapeno.', 'Veg'),
            ('Chicken Pepperoni', 599, 'Non-Veg', 'American classic pepperoni with grilled chicken.', 'Non-Veg'),
            ('Extravaganza', 799, 'Non-Veg', 'The works: all veggies, all meats.', 'Non-Veg')
        ]
        c.executemany("INSERT INTO products (name, price, category, description, type) VALUES (?, ?, ?, ?, ?)", pizzas)

    conn.commit()
    conn.close()

# --- 3. INVENTORY LOGIC (The "Uber" Engine) ---
def deduct_standardized_inventory(cart_items, order_id):
    conn = sqlite3.connect('pizza.db')
    c = conn.cursor()
    log_msg = []

    for item in cart_items:
        size = item.get('size', 'Medium') # Default Medium
        qty = item.get('qty', 1)
        
        # Determine Base Usage from Formula
        usage = STANDARD_USAGE.get(size, STANDARD_USAGE['Medium'])
        
        # 1. Base Deductions (Dough, Sauce, Cheese)
        c.execute("UPDATE ingredients SET quantity = quantity - ? WHERE name='Pizza Dough'", (usage['dough'] * qty,))
        c.execute("UPDATE ingredients SET quantity = quantity - ? WHERE name='Tomato Sauce'", (usage['sauce'] * qty,))
        c.execute("UPDATE ingredients SET quantity = quantity - ? WHERE name='Mozzarella Cheese'", (usage['cheese'] * qty,))
        
        # 2. Topping Logic (Heuristic based on Pizza Name)
        pizza_name = item['name'].lower()
        
        # If it's a known Veggie pizza, deduct veggies
        if 'veg' in pizza_name or 'farmhouse' in pizza_name or 'paneer' in pizza_name or 'margherita' in pizza_name:
            c.execute("UPDATE ingredients SET quantity = quantity - ? WHERE name='Onions'", (usage['topping_veg'] * qty,))
            c.execute("UPDATE ingredients SET quantity = quantity - ? WHERE name='Green Peppers'", (usage['topping_veg'] * qty,))
        
        # If it's Meat, deduct meats
        if 'chicken' in pizza_name or 'pepperoni' in pizza_name or 'non-veg' in pizza_name:
            meat_amount = usage['topping_meat'] * qty
            if 'pepperoni' in pizza_name:
                c.execute("UPDATE ingredients SET quantity = quantity - ? WHERE name='Pepperoni'", (meat_amount,))
            if 'chicken' in pizza_name:
                c.execute("UPDATE ingredients SET quantity = quantity - ? WHERE name='Chicken'", (meat_amount,))

        # 3. Customizations (The Extras)
        if 'extras' in item:
            for extra in item['extras']:
                extra_amount = 30 * qty # 30g for any extra
                
                if 'Cheese' in extra:
                    c.execute("UPDATE ingredients SET quantity = quantity - ? WHERE name='Mozzarella Cheese'", (40 * qty,)) # Extra cheese is 40g
                elif 'Mushrooms' in extra:
                    c.execute("UPDATE ingredients SET quantity = quantity - ? WHERE name='Mushrooms'", (extra_amount,))
                elif 'Olives' in extra:
                    c.execute("UPDATE ingredients SET quantity = quantity - ? WHERE name='Black Olives'", (extra_amount,))
                elif 'Corn' in extra:
                    c.execute("UPDATE ingredients SET quantity = quantity - ? WHERE name='Sweet Corn'", (extra_amount,))
                elif 'Jalapenos' in extra:
                    c.execute("UPDATE ingredients SET quantity = quantity - ? WHERE name='Jalapenos'", (extra_amount,))
                elif 'Paprika' in extra:
                    c.execute("UPDATE ingredients SET quantity = quantity - ? WHERE name='Red Paprika'", (extra_amount,))

        log_msg.append(f"{qty}x {item['name']} ({size})")

    # Audit Log
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    final_msg = f"Order #{order_id}: " + ", ".join(log_msg)
    c.execute("INSERT INTO inventory_logs (message, timestamp) VALUES (?, ?)", (final_msg, timestamp))

    conn.commit()
    conn.close()

init_db()

# --- 4. ROUTES ---

@app.context_processor
def inject_globals():
    count = 0
    if 'cart' in session: count = sum(i.get('qty', 1) for i in session['cart'])
    return dict(cart_count=count)

@app.route('/')
def index():
    if 'user_id' in session and session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('menu'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_id = request.form['login_id'] # Captures either Username or Email
        password = request.form['password']
        
        conn = sqlite3.connect('pizza.db')
        conn.row_factory = sqlite3.Row # Using Row factory to avoid index shifting after ALTER TABLE
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? OR email=?", (login_id, login_id))
        user = c.fetchone()
        conn.close()
        
        if not user:
            flash('Account not found.', 'error')
        elif check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            return redirect(url_for('admin_dashboard') if user['role'] == 'admin' else url_for('menu'))
        else:
            flash('Invalid credentials.', 'error')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        conn = sqlite3.connect('pizza.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Check if Username OR Email already exists
        c.execute("SELECT * FROM users WHERE username=? OR email=?", (username, email))
        existing_user = c.fetchone()
        
        if existing_user:
            if existing_user['username'] == username:
                flash('Username taken.', 'error')
            elif existing_user['email'] == email:
                flash('Email already registered.', 'error')
            conn.close()
            return redirect(url_for('register'))
            
        hashed = generate_password_hash(password)
        try:
            c.execute("INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)", 
                         (username, email, hashed, 'user'))
            conn.commit()
            flash('Account created successfully! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash('An error occurred. Please try again.', 'error')
        finally: 
            conn.close()
            
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/menu')
def menu():
    conn = sqlite3.connect('pizza.db')
    c = conn.cursor()
    c.execute("SELECT * FROM products")
    products = c.fetchall()
    conn.close()
    return render_template('menu.html', products=products)

@app.route('/api/add_to_cart', methods=['POST'])
def add_to_cart():
    if 'user_id' not in session: return jsonify({'status': 'error', 'redirect': '/login'})
    if 'cart' not in session: session['cart'] = []
    
    data = request.json
    found = False
    for item in session['cart']:
        if (item['id'] == data['id'] and item['size'] == data['size'] and 
            item['crust'] == data['crust'] and set(item['extras']) == set(data['extras'])):
            item['qty'] += 1
            item['total_price'] += float(data['total_price'])
            found = True
            break
    if not found:
        data['qty'] = 1
        data['total_price'] = float(data['total_price'])
        session['cart'].append(data)
    
    session.modified = True
    return jsonify({'status': 'success'})

@app.route('/cart')
def cart():
    if 'user_id' not in session: return redirect('/login')
    items = session.get('cart', [])
    total = sum(i['total_price'] for i in items)
    return render_template('cart.html', cart_items=items, total=round(total, 2))

@app.route('/update_cart_qty', methods=['POST'])
def update_qty():
    data = request.json
    idx = int(data['index'])
    if 'cart' in session:
        if data['change'] == -1 and session['cart'][idx]['qty'] == 1:
            del session['cart'][idx]
        else:
            session['cart'][idx]['qty'] += data['change']
            unit_price = session['cart'][idx]['total_price'] / (session['cart'][idx]['qty'] - data['change'])
            session['cart'][idx]['total_price'] = unit_price * session['cart'][idx]['qty']
        session.modified = True
    return jsonify({'status': 'success'})

@app.route('/checkout', methods=['POST'])
def checkout():
    if 'user_id' not in session: return redirect('/login')
    cart = session.get('cart', [])
    if not cart: return redirect('/menu')
    
    total = float(request.form['total'])
    order_type = request.form.get('order_type', 'Pickup')
    
    # NEW: Capture Address (Default to "Counter Pickup" if empty)
    address = request.form.get('address', '').strip() or "Counter Pickup"
    
    conn = sqlite3.connect('pizza.db')
    c = conn.cursor()
    
    # UPDATED SQL: Added 'address' to columns and VALUES
    c.execute("INSERT INTO orders (user_id, total_amount, status, date, items_json, order_type, address) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (session['user_id'], total, 'Pending', datetime.now().strftime("%Y-%m-%d %I:%M %p"), json.dumps(cart), order_type, address))
    
    order_id = c.lastrowid
    conn.commit()
    conn.close()
    
    deduct_standardized_inventory(cart, order_id)
    session.pop('cart', None)
    return render_template('checkout_success.html')

@app.route('/my_orders')
def my_orders():
    if 'user_id' not in session: return redirect('/login')
    conn = sqlite3.connect('pizza.db')
    c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC", (session['user_id'],))
    orders = []
    for o in c.fetchall():
        orders.append(list(o) + [json.loads(o[5])])
    conn.close()
    return render_template('my_orders.html', orders=orders)

# --- NEW: RECEIPT GENERATOR ---
@app.route('/receipt/<int:order_id>')
def order_receipt(order_id):
    if 'user_id' not in session: return redirect('/login')
    
    conn = sqlite3.connect('pizza.db')
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    
    if not order: 
        conn.close()
        return "Order not found", 404
        
    # Get the specific user who made the order for the receipt header
    user = conn.execute("SELECT username FROM users WHERE id=?", (order[1],)).fetchone()
    conn.close()
    
    # Security: Only allow Admin or the Order Owner to see it
    if session['role'] != 'admin' and session['user_id'] != order[1]:
        return "Unauthorized", 403

    items = json.loads(order[5]) if order[5] else []
    subtotal = sum(i['total_price'] for i in items)
    tax = subtotal * 0.05
    
    return render_template('receipt.html', order=order, items=items, user=user, subtotal=subtotal, tax=tax)

# --- ADMIN ROUTES ---
def admin_only():
    return session.get('role') == 'admin'

@app.route('/admin/dashboard')
def admin_dashboard():
    if not admin_only(): return redirect('/login')
    conn = sqlite3.connect('pizza.db')
    c = conn.cursor()
    
    # Basic Stats
    total_orders = c.execute("SELECT count(*) FROM orders").fetchone()[0]
    revenue = c.execute("SELECT sum(total_amount) FROM orders").fetchone()[0] or 0
    pending = c.execute("SELECT count(*) FROM orders WHERE status != 'Delivered'").fetchone()[0]
    low_stock = c.execute("SELECT * FROM ingredients WHERE quantity <= threshold").fetchall()
    
    # --- NEW FIXED ANALYTICS LOGIC ---
    # 1. Get list of valid Pizza names from DB to filter out toppings
    valid_products = {row[0] for row in c.execute("SELECT name FROM products").fetchall()}
    
    all_orders = c.execute("SELECT items_json FROM orders").fetchall()
    item_counter = Counter()
    
    for row in all_orders:
        if row[0]:
            try:
                cart = json.loads(row[0])
                for item in cart:
                    # Only count if the name is in our Products list
                    if item['name'] in valid_products:
                        item_counter[item['name']] += item['qty']
            except: pass
            
    top_item = item_counter.most_common(1)
    best_seller = top_item[0] if top_item else ("No Sales Yet", 0)
    # ---------------------------------
    
    conn.close()
    return render_template('admin/dashboard.html', 
                           total=total_orders, 
                           revenue=round(revenue, 2), 
                           pending=pending, 
                           low_stock=low_stock,
                           best_seller=best_seller)

@app.route('/admin/kitchen')
def admin_kitchen():
    if not admin_only(): return redirect('/login')
    conn = sqlite3.connect('pizza.db')
    c = conn.cursor()
    
    # UPDATED QUERY: Now fetches order_type (idx 6) and address (idx 7)
    # This aligns the indices with my_orders so 'items' is always at index 8
    c.execute("""
        SELECT orders.id, users.username, orders.total_amount, orders.status, orders.date, orders.items_json, orders.order_type, orders.address 
        FROM orders 
        JOIN users ON orders.user_id = users.id 
        WHERE orders.status != 'Delivered' 
        ORDER BY orders.id ASC
    """)
    
    orders = []
    for o in c.fetchall():
        # Append parsed JSON at index 8
        orders.append(list(o) + [json.loads(o[5]) if o[5] else []])
        
    conn.close()
    return render_template('admin/kitchen.html', orders=orders)

@app.route('/admin/update_status', methods=['POST'])
def update_status():
    if not admin_only(): return redirect('/login')
    conn = sqlite3.connect('pizza.db')
    conn.execute("UPDATE orders SET status=? WHERE id=?", (request.form['status'], request.form['order_id']))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_kitchen'))

@app.route('/admin/inventory')
def admin_inventory():
    if not admin_only(): return redirect('/login')
    conn = sqlite3.connect('pizza.db')
    ingredients = conn.execute("SELECT * FROM ingredients ORDER BY name").fetchall()
    # Fetch products so the Recipe dropdowns work
    products = conn.execute("SELECT * FROM products").fetchall()
    logs = conn.execute("SELECT * FROM inventory_logs ORDER BY id DESC LIMIT 20").fetchall()
    conn.close()
    return render_template('admin/inventory.html', ingredients=ingredients, products=products, logs=logs)

# --- INVENTORY CRUD ROUTES ---

@app.route('/admin/ingredient/add', methods=['POST'])
def add_ingredient():
    if not admin_only(): return redirect('/login')
    name = request.form['name']
    qty = float(request.form['quantity'])
    unit = request.form['unit']
    # Capture threshold from form
    threshold = float(request.form.get('threshold', 1000))
    
    conn = sqlite3.connect('pizza.db')
    c = conn.cursor()
    c.execute("INSERT INTO ingredients (name, quantity, unit, threshold) VALUES (?, ?, ?, ?)", (name, qty, unit, threshold))
    
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO inventory_logs (message, timestamp) VALUES (?, ?)", (f"Added new item: {name}", ts))
    
    conn.commit()
    conn.close()
    return redirect(url_for('admin_inventory'))

@app.route('/admin/ingredient/update', methods=['POST'])
def update_ingredient():
    if not admin_only(): return redirect('/login')
    iid = request.form['id']
    change = float(request.form['change_amount'])
    reason = request.form['reason']
    
    conn = sqlite3.connect('pizza.db')
    c = conn.cursor()
    c.execute("UPDATE ingredients SET quantity = quantity + ? WHERE id=?", (change, iid))
    
    name = c.execute("SELECT name FROM ingredients WHERE id=?", (iid,)).fetchone()[0]
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO inventory_logs (message, timestamp) VALUES (?, ?)", (f"Adjusted {name}: {change} ({reason})", ts))
    
    conn.commit()
    conn.close()
    return redirect(url_for('admin_inventory'))


if __name__ == '__main__':
    app.run(debug=True)