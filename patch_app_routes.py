import re

def patch_routes():
    with open("app.py", "r") as f:
        content = f.read()

    # Apply g.shop logic in load_logged_in_user
    before_req_old = """    @app.before_request
    def load_logged_in_user():
        user_id = session.get("user_id")
        if user_id is None:
            g.user = None
        else:
            g.user = get_user_by_id(user_id)"""
    
    before_req_new = """    @app.before_request
    def load_logged_in_user():
        user_id = session.get("user_id")
        if user_id is None:
            g.user = None
            g.shop = None
        else:
            g.user = get_user_by_id(user_id)
            if g.user and g.user.get("shop_id"):
                conn = get_db()
                cur = conn.cursor()
                cur.execute("SELECT * FROM shops WHERE id = ?", (g.user["shop_id"],))
                g.shop = cur.fetchone()
                conn.close()
            else:
                g.shop = None"""
    content = content.replace(before_req_old, before_req_new)

    ctx_processor_old = """    @app.context_processor
    def inject_now():
        return {"current_year": datetime.now().year}"""

    ctx_processor_new = """    @app.context_processor
    def inject_now():
        shop_name = g.shop["name"] if getattr(g, "shop", None) else "Prime Cuts POS"
        return {"current_year": datetime.now().year, "shop_name": shop_name}"""
    content = content.replace(ctx_processor_old, ctx_processor_new)

    # In dashboard, replace WHERE with shop_id filtering if normal user
    dashboard_old = """        cur.execute(
            \"\"\"
            SELECT COALESCE(SUM(total_amount), 0) AS total_sales
            FROM sales
            WHERE sale_datetime BETWEEN ? AND ?
            \"\"\",
            (start.isoformat(), end.isoformat()),
        )"""
    dashboard_new = """        if g.shop:
            cur.execute(
                \"\"\"
                SELECT COALESCE(SUM(total_amount), 0) AS total_sales
                FROM sales
                WHERE shop_id = ? AND sale_datetime BETWEEN ? AND ?
                \"\"\",
                (g.shop["id"], start.isoformat(), end.isoformat()),
            )
        else:
            cur.execute(
                \"\"\"
                SELECT COALESCE(SUM(total_amount), 0) AS total_sales
                FROM sales
                WHERE sale_datetime BETWEEN ? AND ?
                \"\"\",
                (start.isoformat(), end.isoformat()),
            )"""
    content = content.replace(dashboard_old, dashboard_new)

    low_stock_old = """        cur.execute(
            \"\"\"
            SELECT name, stock_quantity
            FROM meat_items
            WHERE stock_quantity <= 10
            ORDER BY stock_quantity ASC
            \"\"\"
        )"""
    low_stock_new = """        if g.shop:
            cur.execute(
                \"\"\"
                SELECT name, stock_quantity
                FROM meat_items
                WHERE shop_id = ? AND stock_quantity <= 10
                ORDER BY stock_quantity ASC
                \"\"\", (g.shop["id"],)
            )
        else:
            cur.execute(
                \"\"\"
                SELECT name, stock_quantity
                FROM meat_items
                WHERE stock_quantity <= 10
                ORDER BY stock_quantity ASC
                \"\"\"
            )"""
    content = content.replace(low_stock_old, low_stock_new)

    top_sold_old = """        cur.execute(
            \"\"\"
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
            \"\"\"
        )"""
    top_sold_new = """        if g.shop:
            cur.execute(
                \"\"\"
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
                \"\"\", (g.shop["id"],)
            )
        else:
            cur.execute(
                \"\"\"
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
                \"\"\"
            )"""
    content = content.replace(top_sold_old, top_sold_new)

    # Super Admin additional routes:
    superadmin_routes = """
    # --- SUPERADMIN ROUTES ---
    @app.route("/shops")
    @login_required
    @superadmin_required
    def shops_list():
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM shops ORDER BY id")
        shops = cur.fetchall()
        
        # also get users per shop
        cur.execute("SELECT shop_id, COUNT(*) as count FROM users GROUP BY shop_id")
        users_count = {row["shop_id"]: row["count"] for row in cur.fetchall()}
        
        conn.close()
        return render_template("shops.html", shops=shops, users_count=users_count)

    @app.route("/shops/add", methods=["GET", "POST"])
    @login_required
    @superadmin_required
    def shop_add():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
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
                    cur.execute("INSERT INTO shops (name) VALUES (?)", (name,))
                    shop_id = cur.lastrowid
                    
                    cur.execute(
                        "INSERT INTO users (shop_id, username, password_hash, role) VALUES (?, ?, ?, ?)",
                        (shop_id, admin_username, generate_password_hash(admin_password), "admin")
                    )
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
            if not name:
                flash("Shop name is required.", "danger")
            else:
                conn = get_db()
                cur = conn.cursor()
                cur.execute("UPDATE shops SET name = ? WHERE id = ?", (name, g.shop["id"]))
                conn.commit()
                conn.close()
                flash("Shop name updated successfully.", "success")
                return redirect(url_for("dashboard"))
                
        return render_template("settings.html", shop_name=g.shop["name"])
"""
    # Insert superadmin routes before the end of register_routes
    # Assuming the last route is get_meat_price
    content = content.replace('def get_meat_price(item_id):', superadmin_routes + '\n    @app.route("/api/meat/<int:item_id>/price", methods=["GET"])\n    @login_required\n    def get_meat_price(item_id):')

    with open("app.py", "w") as f:
        f.write(content)

if __name__ == '__main__':
    patch_routes()
