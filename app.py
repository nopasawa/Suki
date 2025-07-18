import pandas as pd
import qrcode
from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime, timedelta
import os
from functools import wraps

# --- App Initialization & Config ---
app = Flask(__name__)
app.secret_key = "suki_system_secret_key_final_version"

# --- Constants ---
ADULT_PRICE = 260
CHILD_PRICE = 199
EATING_DURATION_MINUTES = 60
ALL_TABLES = [f"T{i:02d}" for i in range(1, 11)] # สร้างรายชื่อโต๊ะทั้งหมด T01-T10

# --- File Paths & User Database ---
DATA_DIR = "data"
MENU_FILE = os.path.join(DATA_DIR, "menu.csv")
TABLES_FILE = os.path.join(DATA_DIR, "tables.csv")
ORDERS_FILE = os.path.join(DATA_DIR, "orders.csv")
QR_CODE_DIR = os.path.join("static", "qrcodes")

USERS = {
    "cashier": {"password": "cashier01", "role": "cashier"},
    "chef": {"password": "chef01", "role": "chef"},
    "admin": {"password": "admin01", "role": "admin"},
}

# --- Helper Function to manage CSV ---
def load_data(file_path, columns):
    if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)
    if not os.path.exists(QR_CODE_DIR): os.makedirs(QR_CODE_DIR)
    try:
        return pd.read_csv(file_path)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        df = pd.DataFrame(columns=columns)
        df.to_csv(file_path, index=False)
        return df

# --- Authentication Decorator ---
def login_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user' not in session:
                flash("กรุณา Login ก่อนเข้าใช้งาน", "warning")
                return redirect(url_for('login'))
            if session['user']['role'] != role:
                flash("คุณไม่มีสิทธิ์เข้าถึงหน้านี้", "danger")
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- Main Routes (Login, Logout, Index) ---
@app.route("/")
def index():
    if 'user' in session:
        role = session['user']['role']
        if role == 'admin': return redirect(url_for('admin_dashboard'))
        if role == 'cashier': return redirect(url_for('cashier_view'))
        if role == 'chef': return redirect(url_for('kitchen_view'))
    return redirect(url_for('login'))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = USERS.get(username)
        if user and user["password"] == password:
            session['user'] = {"username": username, "role": user["role"]}
            flash("Login สำเร็จ!", "success")
            return redirect(url_for('index'))
        else:
            flash("Username หรือ Password ไม่ถูกต้อง", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop('user', None)
    flash("Logout เรียบร้อยแล้ว", "info")
    return redirect(url_for('login'))


# --- Cashier Route ---
@app.route("/cashier", methods=["GET", "POST"])
@login_required('cashier')
def cashier_view():
    table_columns = ['table_number', 'adults', 'children', 'start_time', 'end_time', 'total_price', 'status', 'qr_code_path']
    tables_df = load_data(TABLES_FILE, table_columns)
    new_bill_info = None

    # Ensure date columns are proper datetime objects
    if not tables_df.empty:
        tables_df['start_time'] = pd.to_datetime(tables_df['start_time'], errors='coerce')
        tables_df['end_time'] = pd.to_datetime(tables_df['end_time'], errors='coerce')

    # Check for expired tables
    now = datetime.now()
    valid_tables_df = tables_df.dropna(subset=['end_time']).copy()
    if not valid_tables_df.empty:
        expired_indices = valid_tables_df[valid_tables_df['end_time'] < now].index
        if len(expired_indices) > 0:
            tables_df.loc[expired_indices, 'status'] = 'expired'
            tables_df.to_csv(TABLES_FILE, index=False, date_format='%Y-%m-%d %H:%M:%S')

    # Calculate available tables for the dropdown
    occupied_tables = tables_df['table_number'].tolist()
    available_tables = [table for table in ALL_TABLES if table not in occupied_tables]

    if request.method == "POST":
        table_number = request.form.get("table_number")
        if not table_number or table_number in occupied_tables:
            flash(f"กรุณาเลือกโต๊ะที่ว่าง หรือโต๊ะที่เลือก ({table_number}) ถูกใช้งานไปแล้ว", "danger")
            return redirect(url_for('cashier_view'))

        adults = int(request.form.get("adults", 0))
        children = int(request.form.get("children", 0))
        start_time = datetime.now()
        end_time = start_time + timedelta(minutes=EATING_DURATION_MINUTES)
        total_price = (adults * ADULT_PRICE) + (children * CHILD_PRICE)
        
        qr_relative_path = os.path.join("qrcodes", f"{table_number}.png")
        qr_full_path = os.path.join("static", qr_relative_path)
        menu_url = url_for('menu_view', table_number=table_number, _external=True)
        qrcode.make(menu_url).save(qr_full_path)

        new_bill_dict = {
            "table_number": table_number, "adults": adults, "children": children,
            "start_time": start_time, "end_time": end_time, "total_price": total_price,
            "status": "active", "qr_code_path": qr_relative_path
        }
        new_bill_info = new_bill_dict

        new_bill_df = pd.DataFrame([new_bill_dict])
        updated_tables_df = pd.concat([tables_df, new_bill_df], ignore_index=True)
        
        updated_tables_df.to_csv(TABLES_FILE, index=False, date_format='%Y-%m-%d %H:%M:%S')
        
        flash(f"สร้างบิลสำหรับโต๊ะ {table_number} สำเร็จ!", "success")
        
        final_occupied_tables = updated_tables_df['table_number'].tolist()
        final_available_tables = [table for table in ALL_TABLES if table not in final_occupied_tables]

        return render_template("cashier.html", 
                               tables=updated_tables_df.to_dict('records'),
                               new_bill_info=new_bill_info,
                               available_tables=final_available_tables,
                               ADULT_PRICE=ADULT_PRICE,
                               CHILD_PRICE=CHILD_PRICE)

    return render_template("cashier.html", 
                           tables=tables_df.to_dict('records'), 
                           new_bill_info=None,
                           available_tables=available_tables)


# --- Checkout Route ---
@app.route("/checkout/<string:table_number>", methods=["POST"])
@login_required('cashier')
def checkout(table_number):
    tables_df = load_data(TABLES_FILE, [])
    table_to_remove = tables_df[tables_df['table_number'] == table_number]
    
    if not table_to_remove.empty:
        qr_path = table_to_remove.iloc[0]['qr_code_path']
        full_qr_path = os.path.join('static', qr_path)
        if os.path.exists(full_qr_path):
            os.remove(full_qr_path)
        
        tables_df_after_checkout = tables_df[tables_df['table_number'] != table_number]
        tables_df_after_checkout.to_csv(TABLES_FILE, index=False)
        
        flash(f"โต๊ะ {table_number} เช็คเอาท์เรียบร้อย", "success")
    else:
        flash(f"ไม่พบโต๊ะ {table_number} ในระบบ", "danger")
        
    return redirect(url_for('cashier_view'))

# --- Menu Route ---
@app.route("/menu/<string:table_number>", methods=["GET", "POST"])
def menu_view(table_number):
    menu_df = load_data(MENU_FILE, ['name', 'category'])
    tables_df = load_data(TABLES_FILE, [])
    table_info = tables_df[tables_df['table_number'] == table_number]

    if table_info.empty or table_info.iloc[0]['status'] != 'active':
        return render_template("error.html", message="โต๊ะนี้ยังไม่เปิดใช้งานหรือหมดเวลาแล้ว")

    if request.method == "POST":
        order_columns = ['order_id', 'table_number', 'item_name', 'quantity', 'status']
        orders_df = load_data(ORDERS_FILE, order_columns)
        new_orders = []
        order_time = datetime.now().strftime("%f")
        for item_name, quantity in request.form.items():
            if quantity and int(quantity) > 0:
                new_orders.append({"order_id": f"{table_number}-{item_name[:5]}-{order_time}",
                                   "table_number": table_number, "item_name": item_name,
                                   "quantity": int(quantity), "status": "pending"})
        if new_orders:
            new_orders_df = pd.DataFrame(new_orders)
            orders_df = pd.concat([orders_df, new_orders_df], ignore_index=True)
            orders_df.to_csv(ORDERS_FILE, index=False)
            flash("ส่งรายการอาหารเรียบร้อยแล้ว!", "success")
        return redirect(url_for('menu_view', table_number=table_number))

    # Convert the GroupBy object to a dictionary that the template can iterate through.
    if not menu_df.empty:
        menu_by_category = {category: group_df for category, group_df in menu_df.groupby('category')}
    else:
        menu_by_category = {}
    
    return render_template("menu.html", menu_by_category=menu_by_category, table_number=table_number)

# --- Kitchen Route ---
@app.route("/kitchen")
@login_required('chef')
def kitchen_view():
    orders_df = load_data(ORDERS_FILE, [])
    pending_orders = orders_df[orders_df['status'] == 'pending']
    orders_by_table = {table: group.to_dict('records') for table, group in pending_orders.groupby('table_number')} if not pending_orders.empty else None
    return render_template("kitchen.html", orders_by_table=orders_by_table)

@app.route("/serve_order/<string:order_id>", methods=["POST"])
@login_required('chef')
def serve_order(order_id):
    orders_df = load_data(ORDERS_FILE, [])
    orders_df.loc[orders_df['order_id'] == order_id, 'status'] = 'served'
    orders_df.to_csv(ORDERS_FILE, index=False)
    return redirect(url_for('kitchen_view'))

# --- Admin Routes ---
@app.route("/admin/menu", methods=["GET", "POST"])
@login_required('admin')
def admin_menu():
    menu_df = load_data(MENU_FILE, ['name', 'category'])
    if request.method == "POST":
        item_name = request.form.get("item_name")
        item_category = request.form.get("item_category")
        if item_name and item_category:
            new_item = pd.DataFrame([{'name': item_name, 'category': item_category}])
            menu_df = pd.concat([menu_df, new_item], ignore_index=True)
            menu_df.to_csv(MENU_FILE, index=False)
            flash(f"เพิ่มเมนู '{item_name}' เรียบร้อยแล้ว", "success")
        return redirect(url_for('admin_menu'))
    return render_template("admin_menu.html", menu_items=menu_df.to_dict('records'))

@app.route("/admin/delete/<string:item_name>", methods=["POST"])
@login_required('admin')
def delete_menu_item(item_name):
    menu_df = load_data(MENU_FILE, [])
    menu_df = menu_df[menu_df['name'] != item_name]
    menu_df.to_csv(MENU_FILE, index=False)
    flash(f"ลบเมนู '{item_name}' เรียบร้อยแล้ว", "success")
    return redirect(url_for('admin_menu'))

@app.route("/admin/dashboard")
@login_required('admin')
def admin_dashboard():
    tables_df = load_data(TABLES_FILE, [])
    orders_df = load_data(ORDERS_FILE, [])
    
    total_revenue = tables_df['total_price'].sum() if not tables_df.empty else 0
    total_customers = (tables_df['adults'].sum() + tables_df['children'].sum()) if not tables_df.empty else 0
    total_orders = len(orders_df)
    active_tables_count = len(tables_df)
    
    dashboard_data = {
        "total_revenue": f"{total_revenue:,.2f}",
        "total_customers": f"{total_customers:,.0f}",
        "total_orders": f"{total_orders:,.0f}",
        "active_tables_count": f"{active_tables_count:,.0f}"
    }
    
    return render_template("admin_dashboard.html", data=dashboard_data)

# --- Error Page Route ---
@app.route("/error")
def error_page():
    message = request.args.get('message', 'เกิดข้อผิดพลาดไม่ทราบสาเหตุ')
    return render_template("error.html", message=message)

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')
