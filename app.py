from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json

app = Flask(__name__)
app.secret_key = 'midnight_slice_secure_key'

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect('pizza.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY, username TEXT, password TEXT, role TEXT)''')
    
    # Added description and cuisine
    c.execute('''CREATE TABLE IF NOT EXISTS products 
                 (id INTEGER PRIMARY KEY, name TEXT, price REAL, category TEXT, image TEXT, description TEXT, cuisine TEXT)''')
    
    # Orders now store JSON for complex cart items
    c.execute('''CREATE TABLE IF NOT EXISTS orders 
                 (id INTEGER PRIMARY KEY, user_id INTEGER, total_amount REAL, status TEXT, date TEXT, items_json TEXT)''')
    
    # Admin
    c.execute("SELECT * FROM users WHERE username='admin'")
    if not c.fetchone():
        hashed_pw = generate_password_hash('admin123')
        c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                  ('admin', hashed_pw, 'admin'))
    
    # Enhanced Menu Data
    c.execute("SELECT * FROM products")
    if not c.fetchone():
        pizzas = [
            ('Margherita Classic', 299.00, 'Veg', 'p1.jpg', 'San Marzano tomato sauce, fresh mozzarella, basil, EVOO.', 'Italian'),
            ('Pepperoni Feast', 449.00, 'Non-Veg', 'p2.jpg', 'Double pepperoni, mozzarella, signature spicy sauce.', 'American'),
            ('Spicy Inferno', 499.00, 'Non-Veg', 'p3.jpg', 'Jalapeños, paprika, spicy chicken, hot sauce drizzle.', 'Mexican'),
            ('BBQ Chicken', 479.00, 'Non-Veg', 'p4.jpg', 'Smokey BBQ chicken, red onions, cilantro, cheddar blend.', 'American'),
            ('Veggie Supreme', 399.00, 'Veg', 'p5.jpg', 'Bell peppers, onions, mushrooms, olives, corn.', 'Italian'),
            ('Paneer Tikka', 429.00, 'Veg', 'p6.jpg', 'Marinated paneer, tandoori sauce, onions, mint mayo.', 'Indian'),
            ('Chicken Dominator', 599.00, 'Non-Veg', 'p7.jpg', 'Loaded with chicken tikka, sausage, salami, and herbs.', 'Fusion'),
            ('Cheese Burst', 349.00, 'Veg', 'p8.jpg', 'Overloaded with liquid cheese and mozzarella blend.', 'American')
        ]
        c.executemany("INSERT INTO products (name, price, category, image, description, cuisine) VALUES (?, ?, ?, ?, ?, ?)", pizzas)
        
    conn.commit()
    conn.close()

init_db()

# --- Routes ---

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('menu'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect('pizza.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=?", (username,))
        user = c.fetchone()
        conn.close()
        
        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['role'] = user[3]
            if user[3] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('menu'))
        else:
            flash('Invalid Credentials', 'error')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_pw = generate_password_hash(password)
        
        conn = sqlite3.connect('pizza.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                      (username, hashed_pw, 'user'))
            conn.commit()
            flash('Account created! Login to order.', 'success')
            return redirect(url_for('login'))
        except:
            flash('Username already exists', 'error')
        finally:
            conn.close()
            
    return render_template('register.html')

@app.route('/menu')
def menu():
    conn = sqlite3.connect('pizza.db')
    c = conn.cursor()
    c.execute("SELECT * FROM products")
    products = c.fetchall()
    conn.close()
    return render_template('index.html', products=products)

# NEW: Advanced Add to Cart with Customization
@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Please login first'})
    
    if 'cart' not in session:
        session['cart'] = []
    
    # Get data from JSON request (sent by JavaScript)
    data = request.json
    
    cart_item = {
        'id': data['id'],
        'name': data['name'],
        'base_price': float(data['price']),
        'size': data['size'],
        'crust': data['crust'],
        'extras': data['extras'], # List of extra toppings
        'total_price': float(data['total_price'])
    }
    
    session['cart'].append(cart_item)
    session.modified = True
    
    return jsonify({'status': 'success', 'cart_count': len(session['cart'])})

@app.route('/cart')
def cart():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    cart_items = session.get('cart', [])
    total = sum(item['total_price'] for item in cart_items)
    
    return render_template('cart.html', cart_items=cart_items, total=round(total, 2))

@app.route('/remove_from_cart/<int:index>')
def remove_from_cart(index):
    if 'cart' in session and len(session['cart']) > index:
        del session['cart'][index]
        session.modified = True
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['POST'])
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    cart_items = session.get('cart', [])
    if not cart_items:
        return redirect(url_for('menu'))

    total = float(request.form['total'])
    user_id = session['user_id']
    date_now = datetime.now().strftime("%Y-%m-%d %I:%M %p")
    
    # Store cart items as JSON string in DB for history
    items_json = json.dumps(cart_items)
    
    conn = sqlite3.connect('pizza.db')
    c = conn.cursor()
    c.execute("INSERT INTO orders (user_id, total_amount, status, date, items_json) VALUES (?, ?, ?, ?, ?)", 
              (user_id, total, 'Pending', date_now, items_json))
    conn.commit()
    conn.close()
    
    session.pop('cart', None)
    return redirect(url_for('my_orders'))

@app.route('/my_orders')
def my_orders():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    conn = sqlite3.connect('pizza.db')
    c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC", (session['user_id'],))
    orders = c.fetchall()
    conn.close()
    
    return render_template('order_status.html', orders=orders)

@app.route('/admin')
def admin_dashboard():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    conn = sqlite3.connect('pizza.db')
    c = conn.cursor()
    c.execute("SELECT orders.id, users.username, orders.total_amount, orders.status, orders.date, orders.items_json FROM orders JOIN users ON orders.user_id = users.id ORDER BY orders.id DESC")
    orders = c.fetchall()
    conn.close()
    
    # Process JSON items for display
    formatted_orders = []
    for order in orders:
        try:
            items = json.loads(order[5])
            item_summary = ", ".join([f"{i['size']} {i['name']}" for i in items])
        except:
            item_summary = "Standard Order"
        
        formatted_orders.append(list(order) + [item_summary])

    return render_template('admin.html', orders=formatted_orders)

@app.route('/update_status', methods=['POST'])
def update_status():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    order_id = request.form['order_id']
    new_status = request.form['status']
    
    conn = sqlite3.connect('pizza.db')
    c = conn.cursor()
    c.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id))
    conn.commit()
    conn.close()
    
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5500)