from flask import Flask, request, render_template, send_from_directory, redirect, url_for, flash, session
import time, json, os, secrets, sqlite3

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fallback_secret')

TOKEN_FILE = 'tokens.json'
APK_FOLDER = 'files'
DB_FILE = 'customers.db'
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "embonics@syslabs" 

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS customers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mobile TEXT NOT NULL,
                    product TEXT NOT NULL,
                    purchase_date TEXT NOT NULL
                )''')
    conn.commit()
    conn.close()

init_db()

def load_tokens():
    if not os.path.exists(TOKEN_FILE):
        return {}
    with open(TOKEN_FILE, 'r') as f:
        return json.load(f)

def save_tokens(tokens):
    with open(TOKEN_FILE, 'w') as f:
        json.dump(tokens, f)

@app.route('/login', methods=['GET', 'POST'])
def login():
    # If already logged in, redirect to admin 
    if session.get('logged_in'):
        return redirect(url_for('home'))

    if request.method == 'POST':
        user = request.form['username']
        pwd = request.form['password']
        if user == ADMIN_USERNAME and pwd == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin'))
        else:
            flash("Invalid credentials.")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))


@app.route('/')
def root():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return redirect(url_for('admin'))

@app.route('/admin')
def admin():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    apk_files = [f for f in os.listdir(APK_FOLDER) if f.endswith('.apk')]
    return render_template('admin.html', apk_files=apk_files)

@app.route('/home')
def home():
    apk_files = [f for f in os.listdir(APK_FOLDER) if f.endswith('.apk')]
    return render_template('home.html', apk_files=apk_files)

@app.route('/generate/<filename>')
def generate(filename):
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    apk_path = os.path.join(APK_FOLDER, filename)
    if not os.path.exists(apk_path):
        return "APK not found.", 404

    tokens = load_tokens()
    password = secrets.token_hex(3)  # 6-character code
    tokens[password] = {
        'filename': filename,
        'expires': time.time() + 300  # 5 minutes
    }
    save_tokens(tokens)
    return f"Password for <b>{filename}</b>: <b>{password}</b><br>Valid for 5 minutes.<br><a href='/'>Go Back</a>"


@app.route('/download', methods=['GET', 'POST'])
def download():
    apk_files = [f for f in os.listdir(APK_FOLDER) if f.endswith('.apk')]
    
    if request.method == 'POST':
        password = request.form['password'].strip()
        selected_file = request.form['file']
        tokens = load_tokens()

        if password in tokens:
            entry = tokens[password]
            if time.time() < entry['expires'] and entry['filename'] == selected_file:
                del tokens[password]
                save_tokens(tokens)
                return send_from_directory(APK_FOLDER, selected_file, as_attachment=True)
            else:
                del tokens[password]
                save_tokens(tokens)
                flash("Password expired.")
        else:
            flash("Invalid password.")
        return redirect(url_for('download', file=selected_file))
    
    # GET request
    selected_file = request.args.get('file')
    return render_template('download.html', apk_files=apk_files, selected_file=selected_file)

@app.route('/custdb', methods=['GET', 'POST'])
def custdb():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    conn = sqlite3.connect('customers.db')
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mobile TEXT NOT NULL,
            product TEXT NOT NULL,
            purchase_date TEXT NOT NULL
        )
    ''')

    if request.method == 'POST':
        action = request.form.get('action')
        mobile = request.form.get('mobile', '').strip()
        product = request.form.get('product', '').strip()
        date = request.form.get('date', '').strip()

        if action == 'add':
            if mobile and product and date:
                c.execute("INSERT INTO customers (mobile, product, purchase_date) VALUES (?, ?, ?)",
                          (mobile, product, date))
                conn.commit()
        elif action == 'edit':
            cust_id = request.form.get('id')
            if cust_id and mobile and product and date:
                c.execute("UPDATE customers SET mobile = ?, product = ?, purchase_date = ? WHERE id = ?",
                          (mobile, product, date, cust_id))
                conn.commit()

        conn.close()
        return redirect(url_for('custdb')) 
    c.execute("SELECT * FROM customers")
    customers = c.fetchall()
    conn.close()

    return render_template('custdb.html', customers=customers)



@app.route('/delete_customer/<int:customer_id>', methods=['POST'])
def delete_customer(customer_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    conn = sqlite3.connect('customers.db')
    c = conn.cursor()
    c.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
    conn.commit()
    conn.close()

    return redirect(url_for('custdb'))

if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=10000)
