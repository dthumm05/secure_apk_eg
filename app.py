from flask import Flask, request, render_template, send_from_directory, redirect, url_for, flash, session
import time, json, os, secrets, sqlite3
from datetime import datetime, timedelta

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
    c.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            sno TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            mobile TEXT NOT NULL,
            product TEXT NOT NULL,
            purchase_date TEXT NOT NULL,
            warranty TEXT NOT NULL,
            remark TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('home'))

    if request.method == 'POST':
        user = request.form['username'].strip().lower()
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
    return redirect(url_for('admin')) if session.get('logged_in') else redirect(url_for('login'))

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
    password = secrets.token_hex(3)
    tokens[password] = {
        'filename': filename,
        'expires': time.time() + 300
    }
    save_tokens(tokens)
    return f"Password for <b>{filename}</b>: <b>{password}</b><br>Valid for 5 minutes.<br><a href='/'>Go Back</a>"

def load_tokens():
    return json.load(open(TOKEN_FILE)) if os.path.exists(TOKEN_FILE) else {}

def save_tokens(tokens):
    with open(TOKEN_FILE, 'w') as f:
        json.dump(tokens, f)

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

    return render_template('download.html', apk_files=apk_files, selected_file=request.args.get('file'))

@app.route('/custdb', methods=['GET', 'POST'])
def custdb():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    if request.method == 'POST':
        action = request.form.get('action')
        sno = request.form.get('sno', '').strip()
        name = request.form.get('name', '').strip()
        mobile = request.form.get('mobile', '').strip()
        product = request.form.get('product', '').strip()
        date = request.form.get('date', '').strip()
        warranty = request.form.get('warranty', '1 year')
        remark = request.form.get('remark', '').strip()

        if action == 'add':
            if sno and name and mobile and product and date:
                # Check if sno already exists
                c.execute("SELECT sno FROM customers WHERE sno = ?", (sno,))
                if c.fetchone():
                    flash(f"Customer with S.No. {sno} already exists.")
                else:
                    c.execute("INSERT INTO customers (sno, name, mobile, product, purchase_date, warranty, remark) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (sno, name, mobile, product, date, warranty, remark))
                    conn.commit()
        elif action == 'edit':
            old_sno = request.form.get('id')

            if sno != old_sno:
                c.execute("SELECT sno FROM customers WHERE sno = ?", (sno,))
                if c.fetchone():
                    flash(f"S.No. {sno} is already taken.")
                    return redirect(url_for('custdb'))

            if old_sno and sno and name and mobile and product and date:
                c.execute("""
                          UPDATE customers 
                          SET sno = ?, name = ?, mobile = ?, product = ?, purchase_date = ?, warranty = ?, remark = ? 
                          WHERE sno = ?""",
                        (sno, name, mobile, product, date, warranty, remark, old_sno))
                conn.commit()

            return redirect(url_for('custdb'))

    edit_customer = {
        "id": request.args.get("id", ""),
        "sno": request.args.get("sno", ""),
        "name": request.args.get("name", ""),
        "mobile": request.args.get("mobile", ""),
        "product": request.args.get("product", ""),
        "date": request.args.get("date", ""),
        "warranty": request.args.get("warranty", "1 year"),
        "remark": request.args.get("remark", ""),
        "action": request.args.get("action", "add")
    }

    c.execute("SELECT * FROM customers")
    customers = c.fetchall()
    conn.close()

    return render_template('custdb.html', customers=customers, edit_customer=edit_customer)

@app.route('/delete_customer/<sno>', methods=['POST'])
def delete_customer(sno):
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM customers WHERE sno = ?", (sno,))
    conn.commit()
    conn.close()
    return redirect(url_for('custdb'))

@app.route('/check_warranty', methods=['GET', 'POST'])
def check_warranty():
    records = []
    searched = False

    if request.method == 'POST':
        sno = request.form.get('sno', '').strip()
        mobile = request.form.get('mobile', '').strip()
        name = request.form.get('name', '').strip()
        searched = True

        query = "SELECT sno, name, mobile, product, purchase_date, warranty FROM customers WHERE"
        conditions = []
        params = []

        if sno:
            conditions.append("sno = ?")
            params.append(sno)
        elif mobile:
            conditions.append("mobile = ?")
            params.append(mobile)
        elif name:
            conditions.append("name = ?")
            params.append(name)
        else:
            return render_template("check_warranty.html", records=[], searched=searched)

        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(f"{query} {' OR '.join(conditions)}", params)
        rows = c.fetchall()

        for row in rows:
            purchase_date = datetime.strptime(row['purchase_date'], '%Y-%m-%d')
            try:
                val, unit = row['warranty'].split()
                val = float(val)
                warranty_days = int(val * 30) if 'month' in unit else int(val * 365)
            except:
                warranty_days = 0
            is_valid = datetime.now() <= (purchase_date + timedelta(days=warranty_days))

            records.append({
                'sno': row['sno'],
                'name': row['name'],
                'mobile': row['mobile'],
                'product': row['product'],
                'purchase_date': row['purchase_date'],
                'warranty': row['warranty'],
                'warranty_valid': is_valid
            })

        conn.close()

    return render_template('check_warranty.html', records=records, searched=searched)

if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=10000)

# if __name__ == "__main__":
#     app.run(debug=True)
