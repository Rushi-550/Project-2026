from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'midnight_slice_secure_key'

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect('pizza.db')
    c = conn.cursor()
    
    # Users
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY, username TEXT, password TEXT, role TEXT)''')
    
    # Products
    c.execute('''CREATE TABLE IF NOT EXISTS products 
                 (id INTEGER PRIMARY KEY, name TEXT, price REAL, category TEXT, image TEXT)''')
    
    # Orders
    c.execute('''CREATE TABLE IF NOT EXISTS orders 
                 (id INTEGER PRIMARY KEY, user_id INTEGER, total_amount REAL, status TEXT, date TEXT)''')
    
    # Admin Creation
    c.execute("SELECT * FROM users WHERE username='admin'")
    if not c.fetchone():
        hashed_pw = generate_password_hash('admin123')
        c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                  ('admin', hashed_pw, 'admin'))
    
    # Check/Add Dummy Pizzas
    c.execute("SELECT * FROM products")
    if not c.fetchone():
        pizzas = [
            ('Margherita Classic', 12.99, 'Veg', 'p1.jpg'),
            ('Pepperoni Feast', 15.99, 'Non-Veg', 'p2.jpg'),
            ('Spicy Inferno', 16.50, 'Non-Veg', 'p3.jpg'),
            ('BBQ Chicken', 16.99, 'Non-Veg', 'p4.jpg'),
            ('Veggie Supreme', 14.50, 'Veg', 'p5.jpg'),
            ('Mexican Green Wave', 15.50, 'Veg (Spicy)', 'p6.jpg'),
            ('Chicken Dominator', 18.99, 'Non-Veg', 'p7.jpg'),
            ('Cheese Burst', 13.99, 'Veg', 'p8.jpg')
        ]
        c.executemany("INSERT INTO products (name, price, category, image) VALUES (?, ?, ?, ?)", pizzas)
        
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
            # Restore cart if needed? For now, we clear to avoid stale data
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
    # Allow viewing menu without login, but redirect to login on add
    conn = sqlite3.connect('pizza.db')
    c = conn.cursor()
    c.execute("SELECT * FROM products")
    products = c.fetchall()
    conn.close()
    return render_template('index.html', products=products)

@app.route('/add_to_cart/<int:product_id>')
def add_to_cart(product_id):
    if 'user_id' not in session:
        flash('Please login to order', 'error')
        return redirect(url_for('login'))
    
    if 'cart' not in session:
        session['cart'] = []
    
    session['cart'].append(product_id)
    session.modified = True
    flash('Added to cart!', 'success')
    return redirect(url_for('menu'))

@app.route('/cart')
def cart():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    cart_ids = session.get('cart', [])
    cart_items = []
    total = 0
    
    conn = sqlite3.connect('pizza.db')
    c = conn.cursor()
    
    for pid in cart_ids:
        c.execute("SELECT * FROM products WHERE id=?", (pid,))
        product = c.fetchone()
        if product:
            cart_items.append(product)
            total += product[2]
            
    conn.close()
    return render_template('cart.html', cart_items=cart_items, total=round(total, 2))

@app.route('/checkout', methods=['POST'])
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    total = float(request.form['total'])
    user_id = session['user_id']
    date_now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    conn = sqlite3.connect('pizza.db')
    c = conn.cursor()
    c.execute("INSERT INTO orders (user_id, total_amount, status, date) VALUES (?, ?, ?, ?)", 
              (user_id, total, 'Pending', date_now))
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
    c.execute("SELECT orders.id, users.username, orders.total_amount, orders.status FROM orders JOIN users ON orders.user_id = users.id ORDER BY orders.id DESC")
    orders = c.fetchall()
    conn.close()
    
    return render_template('admin.html', orders=orders)

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
    
    flash(f'Order #{order_id} updated to {new_status}', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)