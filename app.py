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
        else:
            g.user = get_user_by_id(user_id)

    @app.context_processor
    def inject_now():
        return {"current_year": datetime.now().year}

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

    # Users table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'cashier'))
        )
        """
    )

    # Meat inventory
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS meat_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            unit TEXT NOT NULL DEFAULT 'kg',
            price_per_unit REAL NOT NULL DEFAULT 0,
            stock_quantity REAL NOT NULL DEFAULT 0
        )
        """
    )

    # Sales header
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    """Create a default admin account if none exist."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM users")
    count = cur.fetchone()["c"]
    if count == 0:
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (
                "admin",
                generate_password_hash("admin123"),
                "admin",
            ),
        )
        conn.commit()
    conn.close()


def ensure_sample_data():
    """Seed some sample meat items if inventory is empty."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM meat_items")
    count = cur.fetchone()["c"]
    if count == 0:
        cur.executemany(
            """
            INSERT INTO meat_items (name, unit, price_per_unit, stock_quantity)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("Beef", "kg", 12.5, 50),
                ("Chicken", "kg", 6.0, 80),
                ("Pork", "kg", 9.0, 60),
                ("Goat", "kg", 11.0, 40),
            ],
        )
        conn.commit()
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
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)

    return wrapped_view


def register_routes(app: Flask) -> None:
    @app.route("/")
    def index():
        if g.user:
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
        today = date.today()
        start = datetime.combine(today, datetime.min.time())
        end = datetime.combine(today, datetime.max.time())

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT COALESCE(SUM(total_amount), 0) AS total_sales
            FROM sales
            WHERE sale_datetime BETWEEN ? AND ?
            """,
            (start.isoformat(), end.isoformat()),
        )
        total_sales = cur.fetchone()["total_sales"]

        cur.execute(
            """
            SELECT name, stock_quantity
            FROM meat_items
            WHERE stock_quantity <= 10
            ORDER BY stock_quantity ASC
            """
        )
        low_stock_items = cur.fetchall()

        conn.close()

        return render_template(
            "dashboard.html",
            total_sales=total_sales,
            low_stock_items=low_stock_items,
        )

    @app.route("/inventory")
    @login_required
    @admin_required
    def inventory_list():
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM meat_items ORDER BY name ASC")
        items = cur.fetchall()
        conn.close()
        return render_template("inventory.html", items=items)

    @app.route("/inventory/add", methods=["GET", "POST"])
    @login_required
    @admin_required
    def inventory_add():
        if request.method == "POST":
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

            if not name:
                error = "Meat name is required."

            if error:
                flash(error, "danger")
            else:
                conn = get_db()
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO meat_items (name, unit, price_per_unit, stock_quantity)
                    VALUES (?, ?, ?, ?)
                    """,
                    (name, unit, price_val, qty_val),
                )
                conn.commit()
                conn.close()
                flash("Meat item added.", "success")
                return redirect(url_for("inventory_list"))

        return render_template("inventory_form.html", item=None)

    @app.route("/inventory/<int:item_id>/edit", methods=["GET", "POST"])
    @login_required
    @admin_required
    def inventory_edit(item_id):
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM meat_items WHERE id = ?", (item_id,))
        item = cur.fetchone()

        if item is None:
            conn.close()
            flash("Item not found.", "danger")
            return redirect(url_for("inventory_list"))

        if request.method == "POST":
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

            if not name:
                error = "Meat name is required."

            if error:
                flash(error, "danger")
            else:
                cur.execute(
                    """
                    UPDATE meat_items
                    SET name = ?, unit = ?, price_per_unit = ?, stock_quantity = ?
                    WHERE id = ?
                    """,
                    (name, unit, price_val, qty_val, item_id),
                )
                conn.commit()
                conn.close()
                flash("Meat item updated.", "success")
                return redirect(url_for("inventory_list"))

        conn.close()
        return render_template("inventory_form.html", item=item)

    @app.route("/inventory/<int:item_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    def inventory_delete(item_id):
        conn = get_db()
        cur = conn.cursor()
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

    @app.route("/sales/new", methods=["GET", "POST"])
    @login_required
    def new_sale():
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM meat_items ORDER BY name ASC")
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

                conn_item = get_db()
                cur_item = conn_item.cursor()
                cur_item.execute(
                    "SELECT * FROM meat_items WHERE id = ?", (int(item_id),)
                )
                item_row = cur_item.fetchone()
                conn_item.close()

                if item_row is None:
                    error = "Invalid meat item."
                    break

                if qty_val > item_row["stock_quantity"]:
                    error = f"Not enough stock for {item_row['name']}."
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
                flash(error, "danger")
                return render_template(
                    "new_sale.html", meat_items=meat_items, customer_name=customer_name
                )

            # Persist sale and update inventory in a single transaction
            conn = get_db()
            cur = conn.cursor()
            now_iso = datetime.now().isoformat()
            cur.execute(
                """
                INSERT INTO sales (sale_datetime, user_id, customer_name, total_amount)
                VALUES (?, ?, ?, ?)
                """,
                (now_iso, g.user["id"], customer_name or None, total_amount),
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

        conn.close()
        return render_template("new_sale.html", meat_items=meat_items)

    @app.route("/sales/<int:sale_id>/receipt")
    @login_required
    def sale_receipt(sale_id):
        conn = get_db()
        cur = conn.cursor()
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

