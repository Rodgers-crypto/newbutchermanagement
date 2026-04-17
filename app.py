import os
import sqlite3
from datetime import datetime, date, timedelta

from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    session,
    g,
    jsonify,
)
from werkzeug.security import generate_password_hash, check_password_hash


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "butcher_shop.db")


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "change-this-secret-key"
    app.config["DATABASE"] = DB_PATH

    @app.before_request
    def load_logged_in_user():
        user_id = session.get("user_id")
        if user_id is None:
            g.user = None
            g.shop = None
        else:
            g.user = get_user_by_id(user_id)
            if g.user and "shop_id" in g.user.keys() and g.user["shop_id"]:
                conn = get_db()
                cur = conn.cursor()
                cur.execute("SELECT * FROM shops WHERE id = ?", (g.user["shop_id"],))
                g.shop = cur.fetchone()
                conn.close()
            else:
                g.shop = None
                
            if g.shop and 'status' in g.shop.keys() and g.shop['status'] == 'hold':
                if request.endpoint not in ('login', 'static'):
                    session.clear()
                    flash("Your shop is currently on hold. Please contact the Superadmin.", "danger")
                    return redirect(url_for("login"))

    @app.context_processor
    def inject_now():
        shop_name = g.shop["name"] if getattr(g, "shop", None) else "Prime Cuts POS"
        shop_phone = g.shop["phone_number"] if getattr(g, "shop", None) and "phone_number" in g.shop.keys() else ""
        return {"current_year": datetime.now().year, "shop_name": shop_name, "shop_phone": shop_phone}

    register_routes(app)
    init_db()
    ensure_default_admin()
    ensure_sample_data()
    return app


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    # Shops table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS shops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT 'Prime Cuts',
            phone_number TEXT DEFAULT ''
        )
        """
    )

    # Users table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER REFERENCES shops(id),
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('superadmin', 'admin', 'cashier'))
        )
        """
    )

    # Categories table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER REFERENCES shops(id),
            name TEXT NOT NULL
        )
        """
    )

    # Meat inventory (now with category link and shop isolation)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS meat_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER REFERENCES shops(id),
            category_id INTEGER,
            name TEXT NOT NULL,
            unit TEXT NOT NULL DEFAULT 'kg',
            price_per_unit REAL NOT NULL DEFAULT 0,
            stock_quantity REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(category_id) REFERENCES categories(id)
        )
        """
    )

    # Sales header
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER REFERENCES shops(id),
            sale_datetime TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            customer_name TEXT,
            total_amount REAL NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )

    # Sales line items
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL,
            meat_item_id INTEGER NOT NULL,
            quantity REAL NOT NULL,
            unit_price REAL NOT NULL,
            line_total REAL NOT NULL,
            FOREIGN KEY(sale_id) REFERENCES sales(id),
            FOREIGN KEY(meat_item_id) REFERENCES meat_items(id)
        )
        """
    )

    conn.commit()
    conn.close()


def ensure_default_admin():
    """Create default accounts if none exist."""
    conn = get_db()
    cur = conn.cursor()
    
    # Check for admin
    cur.execute("SELECT COUNT(*) AS c FROM users WHERE username = 'admin'")
    if cur.fetchone()["c"] == 0:
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", generate_password_hash("admin123"), "admin"),
        )
    
    # Check for cashier
    cur.execute("SELECT COUNT(*) AS c FROM users WHERE username = 'cashier'")
    if cur.fetchone()["c"] == 0:
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("cashier", generate_password_hash("1234"), "cashier"),
        )
        
    conn.commit()
    conn.close()


def seed_shop_data(shop_id, cur):
    """Seed categories and sample meat items for a specific shop_id."""
    categories = ["Beef", "Chicken", "Goat (Mbuzi)", "Lamb", "Offal/Others"]
    cur.executemany(
        "INSERT INTO categories (shop_id, name) VALUES (?, ?)",
        [(shop_id, cat) for cat in categories]
    )
    
    cur.execute("SELECT id, name FROM categories WHERE shop_id = ?", (shop_id,))
    cat_map = {row["name"]: row["id"] for row in cur.fetchall()}
    
    sample_cuts = [
        # Beef
        (shop_id, cat_map["Beef"], "Beef Ribs", "kg", 800.0, 0),
        (shop_id, cat_map["Beef"], "Beef Tripe (Matumbo)", "kg", 450.0, 0),
        (shop_id, cat_map["Beef"], "Beef with Bone", "kg", 600.0, 0),
        (shop_id, cat_map["Beef"], "Minced Beef", "kg", 750.0, 0),
        # Chicken
        (shop_id, cat_map["Chicken"], "Chicken Breast", "kg", 700.0, 0),
        (shop_id, cat_map["Chicken"], "Chicken Wings", "kg", 550.0, 0),
        (shop_id, cat_map["Chicken"], "Full Broiler Chicken", "pcs", 600.0, 0),
        # Goat
        (shop_id, cat_map["Goat (Mbuzi)"], "Goat Leg", "kg", 900.0, 0),
        (shop_id, cat_map["Goat (Mbuzi)"], "Goat Ribs", "kg", 850.0, 0),
        (shop_id, cat_map["Goat (Mbuzi)"], "Goat Shoulder", "kg", 850.0, 0),
        # Lamb
        (shop_id, cat_map["Lamb"], "Lamb Chops", "kg", 1100.0, 0),
        # Others
        (shop_id, cat_map["Offal/Others"], "Dog Meat (Bones/Fat)", "kg", 200.0, 0),
        (shop_id, cat_map["Offal/Others"], "Oxtail", "kg", 700.0, 0),
    ]
    
    cur.executemany(
        """
        INSERT INTO meat_items (shop_id, category_id, name, unit, price_per_unit, stock_quantity)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        sample_cuts,
    )

def ensure_sample_data():
    """Seed categories and sample meat items if empty."""
    conn = get_db()
    cur = conn.cursor()
    
    # Optionally seed first shop if it exists but is empty
    # SQLite does not error on sqlite_master queries but standard SQL is better.
    try:
        cur.execute("SELECT id FROM shops ORDER BY id LIMIT 1")
        row = cur.fetchone()
        if row:
            shop_id = row["id"]
            cur.execute("SELECT COUNT(*) AS c FROM meat_items WHERE shop_id = ?", (shop_id,))
            if cur.fetchone()["c"] == 0:
                seed_shop_data(shop_id, cur)
                conn.commit()
    except sqlite3.OperationalError:
        pass  # shops table might not exist yet if migrate_proper wasn't run
        
    conn.close()


def get_user_by_username(username):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return row


def get_user_by_id(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row


def get_all_users():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users ORDER BY username ASC")
    rows = cur.fetchall()
    conn.close()
    return rows


def login_required(view):
    from functools import wraps

    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def admin_required(view):
    from functools import wraps

    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login"))
        if g.user["role"] != "admin":
            flash("You do not have permission to access this page.", "danger")
            if g.user["role"] == "superadmin":
                return redirect(url_for("shops_list"))
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)

    return wrapped_view


def superadmin_required(view):
    from functools import wraps

    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login"))
        if g.user["role"] != "superadmin":
            flash("Superadmin privileges required.", "danger")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)

    return wrapped_view


def register_routes(app: Flask) -> None:
    @app.route("/")
    def index():
        if g.user:
            if g.user["role"] == "superadmin":
                return redirect(url_for("shops_list"))
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            error = None
            user = get_user_by_username(username)

            if not username or not password:
                error = "Username and password are required."
            elif user is None or not check_password_hash(user["password_hash"], password):
                error = "Invalid username or password."

            if error:
                flash(error, "danger")
            else:
                session.clear()
                session["user_id"] = user["id"]
                session["role"] = user["role"]
                flash(f"Welcome, {user['username']}!", "success")
                if user["role"] == "superadmin":
                    return redirect(url_for("shops_list"))
                return redirect(url_for("dashboard"))

        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        session.clear()
        flash("You have been logged out.", "info")
        return redirect(url_for("login"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        if g.user["role"] == "superadmin":
            return redirect(url_for("shops_list"))
            
        today = date.today()
        start = datetime.combine(today, datetime.min.time())
        end = datetime.combine(today, datetime.max.time())

        conn = get_db()
        cur = conn.cursor()

        if g.shop:
            cur.execute(
                """
                SELECT COALESCE(SUM(total_amount), 0) AS total_sales
                FROM sales
                WHERE shop_id = ? AND sale_datetime BETWEEN ? AND ?
                """,
                (g.shop["id"], start.isoformat(), end.isoformat()),
            )
        else:
            cur.execute(
                """
                SELECT COALESCE(SUM(total_amount), 0) AS total_sales
                FROM sales
                WHERE sale_datetime BETWEEN ? AND ?
                """,
                (start.isoformat(), end.isoformat()),
            )
        total_sales = cur.fetchone()["total_sales"]

        if g.shop:
            cur.execute(
                """
                SELECT name, stock_quantity
                FROM meat_items
                WHERE shop_id = ? AND stock_quantity <= 10
                ORDER BY stock_quantity ASC
                """, (g.shop["id"],)
            )
        else:
            cur.execute(
                """
                SELECT name, stock_quantity
                FROM meat_items
                WHERE stock_quantity <= 10
                ORDER BY stock_quantity ASC
                """
            )
        low_stock_items = cur.fetchall()

        # Top 5 sold cuts (Last 24 hours, min 5 sales threshold)
        if g.shop:
            cur.execute(
                """
                SELECT m.name, c.name as category_name, SUM(si.quantity) as total_qty, COUNT(si.id) as sale_count
                FROM sale_items si
                JOIN sales s ON si.sale_id = s.id
                JOIN meat_items m ON si.meat_item_id = m.id
                JOIN categories c ON m.category_id = c.id
                WHERE s.shop_id = ? AND s.sale_datetime >= datetime('now', '-1 day')
                GROUP BY m.id
                HAVING sale_count >= 5
                ORDER BY total_qty DESC
                LIMIT 5
                """, (g.shop["id"],)
            )
        else:
            cur.execute(
                """
                SELECT m.name, c.name as category_name, SUM(si.quantity) as total_qty, COUNT(si.id) as sale_count
                FROM sale_items si
                JOIN sales s ON si.sale_id = s.id
                JOIN meat_items m ON si.meat_item_id = m.id
                JOIN categories c ON m.category_id = c.id
                WHERE s.sale_datetime >= datetime('now', '-1 day')
                GROUP BY m.id
                HAVING sale_count >= 5
                ORDER BY total_qty DESC
                LIMIT 5
                """
            )
        top_sold_cuts = cur.fetchall()

        conn.close()

        return render_template(
            "dashboard.html",
            total_sales=total_sales,
            low_stock_items=low_stock_items,
            top_sold_cuts=top_sold_cuts,
        )

    @app.route("/inventory")
    @login_required
    @admin_required
    def inventory_list():
        conn = get_db()
        cur = conn.cursor()
        if g.shop:
            cur.execute("""
                SELECT m.*, c.name AS category_name 
                FROM meat_items m
                LEFT JOIN categories c ON m.category_id = c.id
                WHERE m.shop_id = ?
                ORDER BY c.name, m.name ASC
            """, (g.shop["id"],))
        else:
            cur.execute("""
                SELECT m.*, c.name AS category_name 
                FROM meat_items m
                LEFT JOIN categories c ON m.category_id = c.id
                ORDER BY c.name, m.name ASC
            """)
        items = cur.fetchall()
        conn.close()
        return render_template("inventory.html", items=items)

    @app.route("/inventory/add", methods=["GET", "POST"])
    @login_required
    @admin_required
    def inventory_add():
        conn = get_db()
        cur = conn.cursor()
        if g.shop:
            cur.execute("SELECT * FROM categories WHERE shop_id = ? ORDER BY name ASC", (g.shop["id"],))
        else:
            cur.execute("SELECT * FROM categories ORDER BY name ASC")
        categories = cur.fetchall()

        if request.method == "POST":
            category_name = request.form.get("category_name", "").strip()
            name = request.form.get("name", "").strip()
            unit = request.form.get("unit", "kg").strip() or "kg"
            price_per_unit = request.form.get("price_per_unit", "0").strip()
            stock_quantity = request.form.get("stock_quantity", "0").strip()

            error = None
            try:
                price_val = float(price_per_unit)
                qty_val = float(stock_quantity)
                if price_val < 0 or qty_val < 0:
                    error = "Price and quantity must be non-negative."
            except ValueError:
                error = "Price and quantity must be numeric."

            if not name or not category_name:
                error = "Category and name are required."

            if not error:
                shop_id_val = g.shop["id"] if g.shop else None
                if shop_id_val:
                    cur.execute("SELECT id FROM categories WHERE name = ? AND shop_id = ?", (category_name, shop_id_val))
                else:
                    cur.execute("SELECT id FROM categories WHERE name = ? AND shop_id IS NULL", (category_name,))
                cat_row = cur.fetchone()
                if cat_row:
                    category_id = cat_row["id"]
                else:
                    cur.execute("INSERT INTO categories (shop_id, name) VALUES (?, ?)", (shop_id_val, category_name))
                    category_id = cur.lastrowid

            if error:
                flash(error, "danger")
            else:
                cur.execute(
                    """
                    INSERT INTO meat_items (shop_id, category_id, name, unit, price_per_unit, stock_quantity)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (g.shop["id"] if g.shop else None, category_id, name, unit, price_val, qty_val),
                )
                conn.commit()
                conn.close()
                flash("Meat item added.", "success")
                return redirect(url_for("inventory_list"))

        conn.close()
        return render_template("inventory_form.html", item=None, categories=categories)

    @app.route("/inventory/<int:item_id>/edit", methods=["GET", "POST"])
    @login_required
    @admin_required
    def inventory_edit(item_id):
        conn = get_db()
        cur = conn.cursor()
        if g.shop:
            cur.execute("""
                SELECT m.*, c.name as category_name 
                FROM meat_items m 
                LEFT JOIN categories c ON m.category_id = c.id 
                WHERE m.id = ? AND m.shop_id = ?
            """, (item_id, g.shop["id"]))
        else:
            cur.execute("""
                SELECT m.*, c.name as category_name 
                FROM meat_items m 
                LEFT JOIN categories c ON m.category_id = c.id 
                WHERE m.id = ?
            """, (item_id,))
        item = cur.fetchone()

        if item is None:
            conn.close()
            flash("Item not found.", "danger")
            return redirect(url_for("inventory_list"))

        # Fetch categories for the form
        if g.shop:
            cur.execute("SELECT * FROM categories WHERE shop_id = ? ORDER BY name ASC", (g.shop["id"],))
        else:
            cur.execute("SELECT * FROM categories ORDER BY name ASC")
        categories = cur.fetchall()

        if request.method == "POST":
            category_name = request.form.get("category_name", "").strip()
            name = request.form.get("name", "").strip()
            unit = request.form.get("unit", "kg").strip() or "kg"
            price_per_unit = request.form.get("price_per_unit", "0").strip()
            stock_quantity = request.form.get("stock_quantity", "0").strip()

            error = None
            try:
                price_val = float(price_per_unit)
                qty_val = float(stock_quantity)
                if price_val < 0 or qty_val < 0:
                    error = "Price and quantity must be non-negative."
            except ValueError:
                error = "Price and quantity must be numeric."

            if not name or not category_name:
                error = "Category and name are required."

            if not error:
                shop_id_val = g.shop["id"] if g.shop else None
                if shop_id_val:
                    cur.execute("SELECT id FROM categories WHERE name = ? AND shop_id = ?", (category_name, shop_id_val))
                else:
                    cur.execute("SELECT id FROM categories WHERE name = ? AND shop_id IS NULL", (category_name,))
                cat_row = cur.fetchone()
                if cat_row:
                    category_id = cat_row["id"]
                else:
                    cur.execute("INSERT INTO categories (shop_id, name) VALUES (?, ?)", (shop_id_val, category_name))
                    category_id = cur.lastrowid

            if error:
                flash(error, "danger")
            else:
                cur.execute(
                    """
                    UPDATE meat_items
                    SET category_id = ?, name = ?, unit = ?, price_per_unit = ?, stock_quantity = ?
                    WHERE id = ?
                    """,
                    (category_id, name, unit, price_val, qty_val, item_id),
                )
                conn.commit()
                conn.close()
                flash("Meat item updated.", "success")
                return redirect(url_for("inventory_list"))

        conn.close()
        return render_template("inventory_form.html", item=item, categories=categories)

    @app.route("/inventory/<int:item_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    def inventory_delete(item_id):
        conn = get_db()
        cur = conn.cursor()
        if g.shop:
            cur.execute("SELECT * FROM meat_items WHERE id = ? AND shop_id = ?", (item_id, g.shop["id"]))
        else:
            cur.execute("SELECT * FROM meat_items WHERE id = ?", (item_id,))
        item = cur.fetchone()

        if item is None:
            conn.close()
            flash("Item not found.", "danger")
            return redirect(url_for("inventory_list"))

        cur.execute("DELETE FROM meat_items WHERE id = ?", (item_id,))
        conn.commit()
        conn.close()
        flash(f"Item '{item['name']}' deleted.", "success")
        return redirect(url_for("inventory_list"))

    @app.route("/users")
    @login_required
    @admin_required
    def users_list():
        conn = get_db()
        cur = conn.cursor()
        if g.shop:
            cur.execute("SELECT * FROM users WHERE shop_id = ? ORDER BY username ASC", (g.shop["id"],))
        else:
            cur.execute("SELECT * FROM users ORDER BY username ASC")
        users = cur.fetchall()
        conn.close()
        return render_template("users.html", users=users)

    @app.route("/users/add", methods=["GET", "POST"])
    @login_required
    @admin_required
    def user_add():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            role = request.form.get("role", "cashier")

            error = None
            if not username or not password:
                error = "Username and password are required."
            elif get_user_by_username(username) is not None:
                error = f"User {username} is already registered."

            if error:
                flash(error, "danger")
            else:
                conn = get_db()
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO users (shop_id, username, password_hash, role) VALUES (?, ?, ?, ?)",
                    (g.shop["id"] if g.shop else None, username, generate_password_hash(password), role),
                )
                conn.commit()
                conn.close()
                flash("User created successfully.", "success")
                return redirect(url_for("users_list"))

        return render_template("user_form.html", user=None)

    @app.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
    @login_required
    @admin_required
    def user_edit(user_id):
        conn = get_db()
        cur = conn.cursor()
        if g.shop:
            cur.execute("SELECT * FROM users WHERE id = ? AND shop_id = ?", (user_id, g.shop["id"]))
        else:
            cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cur.fetchone()

        if user is None:
            conn.close()
            flash("User not found.", "danger")
            return redirect(url_for("users_list"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            role = request.form.get("role", user["role"])

            error = None
            if not username:
                error = "Username is required."
            
            # Check if username changed and if the new one exists
            if not error and username != user["username"]:
                if get_user_by_username(username) is not None:
                    error = f"User {username} is already registered."

            if error:
                flash(error, "danger")
            else:
                if password:
                    cur.execute(
                        "UPDATE users SET username = ?, password_hash = ?, role = ? WHERE id = ?",
                        (username, generate_password_hash(password), role, user_id),
                    )
                else:
                    cur.execute(
                        "UPDATE users SET username = ?, role = ? WHERE id = ?",
                        (username, role, user_id),
                    )
                conn.commit()
                conn.close()
                flash("User updated successfully.", "success")
                return redirect(url_for("users_list"))

        conn.close()
        return render_template("user_form.html", user=user)

    @app.route("/users/<int:user_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    def user_delete(user_id):
        if g.user["id"] == user_id:
            flash("You cannot delete yourself.", "danger")
            return redirect(url_for("users_list"))

        conn = get_db()
        cur = conn.cursor()
        if g.shop:
            cur.execute("SELECT * FROM users WHERE id = ? AND shop_id = ?", (user_id, g.shop["id"]))
        else:
            cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cur.fetchone()

        if user is None:
            conn.close()
            flash("User not found.", "danger")
            return redirect(url_for("users_list"))

        # Optional: check if user has sales
        cur.execute("SELECT COUNT(*) as count FROM sales WHERE user_id = ?", (user_id,))
        if cur.fetchone()["count"] > 0:
            conn.close()
            flash("Cannot delete user who has recorded sales. Consider changing their password or role instead.", "danger")
            return redirect(url_for("users_list"))

        cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        flash(f"User '{user['username']}' deleted.", "success")
        return redirect(url_for("users_list"))

    @app.route("/sales/new", methods=["GET", "POST"])
    @login_required
    def new_sale():
        if g.user["role"] == "superadmin":
            flash("Superadmins cannot make sales. Their work is to manage the shops.", "warning")
            return redirect(url_for("shops_list"))

        conn = get_db()
        cur = conn.cursor()
        
        # Fetch categories
        if g.shop:
            cur.execute("SELECT * FROM categories WHERE shop_id = ? ORDER BY name ASC", (g.shop["id"],))
        else:
            cur.execute("SELECT * FROM categories ORDER BY name ASC")
        categories = cur.fetchall()

        # Fetch all meat items with category name
        if g.shop:
            cur.execute("""
                SELECT m.*, c.name AS category_name 
                FROM meat_items m
                LEFT JOIN categories c ON m.category_id = c.id
                WHERE m.shop_id = ?
                ORDER BY c.name, m.name
            """, (g.shop["id"],))
        else:
            cur.execute("""
                SELECT m.*, c.name AS category_name 
                FROM meat_items m
                LEFT JOIN categories c ON m.category_id = c.id
                ORDER BY c.name, m.name
            """)
        meat_items = cur.fetchall()

        if request.method == "POST":
            customer_name = request.form.get("customer_name", "").strip()

            item_ids = request.form.getlist("item_id")
            quantities = request.form.getlist("quantity")
            unit_prices = request.form.getlist("unit_price")

            line_items = []
            total_amount = 0.0
            error = None

            if not item_ids:
                error = "At least one item is required."

            if not error:
                for idx, item_id in enumerate(item_ids):
                    if not item_id:
                        continue
                    qty_str = quantities[idx]
                    price_str = unit_prices[idx]
                    try:
                        qty_val = float(qty_str)
                        price_val = float(price_str)
                        if qty_val <= 0 or price_val < 0:
                            error = "Quantity must be positive and price must be non-negative."
                            break
                    except ValueError:
                        error = "Quantity and price must be numeric."
                        break

                    # Fetch item using the EXISTING connection
                    cur.execute(
                        "SELECT * FROM meat_items WHERE id = ?", (int(item_id),)
                    )
                    item_row = cur.fetchone()

                    if item_row is None:
                        error = "Invalid meat item."
                        break

                    # Strict stock check
                    current_stock = item_row["stock_quantity"]
                    if current_stock <= 0:
                        error = f"Item {item_row['name']} is out of stock."
                        break

                    # Use a small epsilon for floating point comparison (e.g., 0.0001)
                    if qty_val > current_stock + 0.0001:
                        error = f"Not enough stock for {item_row['name']} (Requested: {qty_val}, Available: {current_stock})."
                        break

                    line_total = qty_val * price_val
                    total_amount += line_total
                    line_items.append(
                        {
                            "meat_item_id": int(item_id),
                            "name": item_row["name"],
                            "quantity": qty_val,
                            "unit_price": price_val,
                            "line_total": line_total,
                        }
                    )

            if error:
                conn.close()
                flash(error, "danger")
                return render_template(
                    "new_sale.html", meat_items=meat_items, categories=categories, customer_name=customer_name
                )

            try:
                # Persist sale and update inventory in a single transaction
                now_iso = datetime.now().isoformat()
                cur.execute(
                    """
                    INSERT INTO sales (shop_id, sale_datetime, user_id, customer_name, total_amount)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (g.shop["id"] if g.shop else None, now_iso, g.user["id"], customer_name or None, total_amount),
                )
                sale_id = cur.lastrowid

                for li in line_items:
                    cur.execute(
                        """
                        INSERT INTO sale_items
                        (sale_id, meat_item_id, quantity, unit_price, line_total)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            sale_id,
                            li["meat_item_id"],
                            li["quantity"],
                            li["unit_price"],
                            li["line_total"],
                        ),
                    )
                    # Deduct stock
                    cur.execute(
                        """
                        UPDATE meat_items
                        SET stock_quantity = stock_quantity - ?
                        WHERE id = ?
                        """,
                        (li["quantity"], li["meat_item_id"]),
                    )

                conn.commit()
                conn.close()
                flash("Sale recorded successfully.", "success")
                return redirect(url_for("sale_receipt", sale_id=sale_id))
            except Exception as e:
                conn.rollback()
                conn.close()
                flash(f"An error occurred: {str(e)}", "danger")
                return render_template("new_sale.html", meat_items=meat_items, categories=categories)

        conn.close()
        return render_template("new_sale.html", meat_items=meat_items, categories=categories)

    @app.route("/sales/<int:sale_id>/receipt")
    @login_required
    def sale_receipt(sale_id):
        if g.user["role"] == "superadmin":
            return redirect(url_for("shops_list"))
            
        conn = get_db()
        cur = conn.cursor()
        if g.shop:
            cur.execute(
                """
                SELECT s.*, u.username
                FROM sales s
                JOIN users u ON s.user_id = u.id
                WHERE s.id = ? AND s.shop_id = ?
                """,
                (sale_id, g.shop["id"]),
            )
        else:
            cur.execute(
                """
                SELECT s.*, u.username
                FROM sales s
                JOIN users u ON s.user_id = u.id
                WHERE s.id = ?
                """,
                (sale_id,),
            )
        sale = cur.fetchone()
        if sale is None:
            conn.close()
            flash("Sale not found.", "danger")
            return redirect(url_for("dashboard"))

        cur.execute(
            """
            SELECT si.*, m.name, m.unit
            FROM sale_items si
            JOIN meat_items m ON si.meat_item_id = m.id
            WHERE si.sale_id = ?
            """,
            (sale_id,),
        )
        items = cur.fetchall()
        conn.close()
        return render_template("receipt.html", sale=sale, items=items)

    @app.route("/reports", methods=["GET", "POST"])
    @login_required
    def reports():
        if g.user["role"] == "superadmin":
            flash("Superadmins cannot access shop reports.", "warning")
            return redirect(url_for("shops_list"))
            
        period = request.values.get("period", "daily")
        today = date.today()

        if period == "weekly":
            start_date = today - timedelta(days=today.weekday())
        elif period == "monthly":
            start_date = today.replace(day=1)
        else:  # daily
            start_date = today

        end_date = today
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        conn = get_db()
        cur = conn.cursor()

        if g.shop:
            cur.execute(
                """
                SELECT
                    DATE(sale_datetime) AS sale_date,
                    COUNT(*) AS num_sales,
                    SUM(total_amount) AS total_sales
                FROM sales
                WHERE shop_id = ? AND sale_datetime BETWEEN ? AND ?
                GROUP BY DATE(sale_datetime)
                ORDER BY sale_date ASC
                """,
                (g.shop["id"], start_dt.isoformat(), end_dt.isoformat()),
            )
        else:
            cur.execute(
                """
                SELECT
                    DATE(sale_datetime) AS sale_date,
                    COUNT(*) AS num_sales,
                    SUM(total_amount) AS total_sales
                FROM sales
                WHERE sale_datetime BETWEEN ? AND ?
                GROUP BY DATE(sale_datetime)
                ORDER BY sale_date ASC
                """,
                (start_dt.isoformat(), end_dt.isoformat()),
            )
        summary_rows = cur.fetchall()

        if g.shop:
            cur.execute(
                """
                SELECT
                    m.name,
                    SUM(si.quantity) AS total_qty,
                    SUM(si.line_total) AS total_amount
                FROM sale_items si
                JOIN meat_items m ON si.meat_item_id = m.id
                JOIN sales s ON si.sale_id = s.id
                WHERE s.shop_id = ? AND s.sale_datetime BETWEEN ? AND ?
                GROUP BY m.name
                ORDER BY total_amount DESC
                """,
                (g.shop["id"], start_dt.isoformat(), end_dt.isoformat()),
            )
        else:
            cur.execute(
                """
                SELECT
                    m.name,
                    SUM(si.quantity) AS total_qty,
                    SUM(si.line_total) AS total_amount
                FROM sale_items si
                JOIN meat_items m ON si.meat_item_id = m.id
                JOIN sales s ON si.sale_id = s.id
                WHERE s.sale_datetime BETWEEN ? AND ?
                GROUP BY m.name
                ORDER BY total_amount DESC
                """,
                (start_dt.isoformat(), end_dt.isoformat()),
            )
        by_item_rows = cur.fetchall()

        conn.close()

        return render_template(
            "reports.html",
            period=period,
            start_date=start_date,
            end_date=end_date,
            summary_rows=summary_rows,
            by_item_rows=by_item_rows,
        )

    # --- SUPERADMIN ROUTES ---
    @app.route("/shops")
    @login_required
    @superadmin_required
    def shops_list():
        conn = get_db()
        cur = conn.cursor()
        
        today_str = datetime.now().strftime('%Y-%m-%d') + '%'
        
        cur.execute("""
            SELECT s.*, 
                   (SELECT COUNT(*) FROM users u WHERE u.shop_id = s.id) as users_count,
                   (SELECT SUM(total_amount) FROM sales sa WHERE sa.shop_id = s.id AND sa.sale_datetime LIKE ?) as total_revenue,
                   (SELECT COUNT(*) FROM sales sa WHERE sa.shop_id = s.id AND sa.sale_datetime LIKE ?) as sales_count
            FROM shops s 
            ORDER BY s.id
        """, (today_str, today_str))
        shops = cur.fetchall()
        
        conn.close()
        return render_template("shops.html", shops=shops)

    @app.route("/shops/<int:shop_id>/toggle_status", methods=["POST"])
    @login_required
    @superadmin_required
    def shop_toggle_status(shop_id):
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT status, name FROM shops WHERE id = ?", (shop_id,))
        shop = cur.fetchone()
        if shop:
            new_status = 'active' if 'status' in shop.keys() and shop['status'] == 'hold' else 'hold'
            cur.execute("UPDATE shops SET status = ? WHERE id = ?", (new_status, shop_id))
            conn.commit()
            flash(f"Shop {shop['name']} status updated to {new_status}.", "success")
        else:
            flash("Shop not found.", "danger")
        conn.close()
        return redirect(url_for("shops_list"))

    @app.route("/shops/<int:shop_id>/delete", methods=["POST"])
    @login_required
    @superadmin_required
    def shop_delete(shop_id):
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM shops WHERE id = ?", (shop_id,))
        cur.execute("DELETE FROM users WHERE shop_id = ?", (shop_id,))
        cur.execute("DELETE FROM meat_items WHERE shop_id = ?", (shop_id,))
        cur.execute("DELETE FROM categories WHERE shop_id = ?", (shop_id,))
        cur.execute("DELETE FROM sales WHERE shop_id = ?", (shop_id,))
        cur.execute("DELETE FROM sale_items WHERE sale_id IN (SELECT id FROM sales WHERE shop_id = ?)", (shop_id,))
        conn.commit()
        conn.close()
        flash("Shop and all its associated data have been permanently deleted.", "success")
        return redirect(url_for("shops_list"))

    @app.route("/shops/add", methods=["GET", "POST"])
    @login_required
    @superadmin_required
    def shop_add():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            phone_number = request.form.get("phone_number", "").strip()
            admin_username = request.form.get("admin_username", "").strip()
            admin_password = request.form.get("admin_password", "")
            
            if not name or not admin_username or not admin_password:
                flash("All fields are required.", "danger")
            else:
                if get_user_by_username(admin_username):
                    flash("Username already exists.", "danger")
                else:
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("INSERT INTO shops (name, phone_number) VALUES (?, ?)", (name, phone_number))
                    shop_id = cur.lastrowid
                    
                    cur.execute(
                        "INSERT INTO users (shop_id, username, password_hash, role) VALUES (?, ?, ?, ?)",
                        (shop_id, admin_username, generate_password_hash(admin_password), "admin")
                    )
                    
                    # Seed initial categories and stock for this shop
                    seed_shop_data(shop_id, cur)
                    
                    conn.commit()
                    conn.close()
                    flash(f"Shop '{name}' created with admin '{admin_username}'.", "success")
                    return redirect(url_for("shops_list"))
        return render_template("shop_form.html")

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    @admin_required
    def settings():
        if not g.shop:
            flash("Superadmins cannot access shop settings.", "warning")
            return redirect(url_for("dashboard"))
            
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            phone_number = request.form.get("phone_number", "").strip()
            if not name:
                flash("Shop name is required.", "danger")
            else:
                conn = get_db()
                cur = conn.cursor()
                cur.execute("UPDATE shops SET name = ?, phone_number = ? WHERE id = ?", (name, phone_number, g.shop["id"]))
                conn.commit()
                conn.close()
                flash("Shop settings updated successfully.", "success")
                return redirect(url_for("dashboard"))
                
        return render_template("settings.html", shop_name=g.shop["name"], shop_phone=g.shop["phone_number"] if "phone_number" in g.shop.keys() else "")

    @app.route("/api/meat/<int:item_id>/price", methods=["GET"])
    @login_required
    def get_meat_price(item_id):
        """Simple JSON endpoint to help JS auto-fill price from inventory."""
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, unit, price_per_unit, stock_quantity FROM meat_items WHERE id = ?",
            (item_id,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return jsonify({"error": "Not found"}), 404
        return jsonify(
            {
                "id": row["id"],
                "name": row["name"],
                "unit": row["unit"],
                "price_per_unit": row["price_per_unit"],
                "stock_quantity": row["stock_quantity"],
            }
        )


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)

