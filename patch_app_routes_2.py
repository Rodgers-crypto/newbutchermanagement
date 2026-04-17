import re

def patch_routes_2():
    with open("app.py", "r") as f:
        content = f.read()

    # Patches for user_add
    user_add_old = """                cur.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    (username, generate_password_hash(password), role),
                )"""
    user_add_new = """                cur.execute(
                    "INSERT INTO users (shop_id, username, password_hash, role) VALUES (?, ?, ?, ?)",
                    (g.shop["id"] if g.shop else None, username, generate_password_hash(password), role),
                )"""
    content = content.replace(user_add_old, user_add_new)

    # Patches for user_edit (don't strictly need to change query, just fetch the user matching shop_id if g.shop is set)
    user_edit_old = """    def user_edit(user_id):
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cur.fetchone()"""
    user_edit_new = """    def user_edit(user_id):
        conn = get_db()
        cur = conn.cursor()
        if g.shop:
            cur.execute("SELECT * FROM users WHERE id = ? AND shop_id = ?", (user_id, g.shop["id"]))
        else:
            cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cur.fetchone()"""
    content = content.replace(user_edit_old, user_edit_new)

    user_delete_old = """    def user_delete(user_id):
        if g.user["id"] == user_id:
            flash("You cannot delete yourself.", "danger")
            return redirect(url_for("users_list"))

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cur.fetchone()"""
    user_delete_new = """    def user_delete(user_id):
        if g.user["id"] == user_id:
            flash("You cannot delete yourself.", "danger")
            return redirect(url_for("users_list"))

        conn = get_db()
        cur = conn.cursor()
        if g.shop:
            cur.execute("SELECT * FROM users WHERE id = ? AND shop_id = ?", (user_id, g.shop["id"]))
        else:
            cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cur.fetchone()"""
    content = content.replace(user_delete_old, user_delete_new)

    # Patches for new_sale
    new_sale_cat_old = """        # Fetch categories
        cur.execute("SELECT * FROM categories ORDER BY name ASC")
        categories = cur.fetchall()

        # Fetch all meat items with category name
        cur.execute(\"\"\"
            SELECT m.*, c.name AS category_name 
            FROM meat_items m
            LEFT JOIN categories c ON m.category_id = c.id
            ORDER BY c.name, m.name
        \"\"\")"""
    new_sale_cat_new = """        # Fetch categories
        if g.shop:
            cur.execute("SELECT * FROM categories WHERE shop_id = ? ORDER BY name ASC", (g.shop["id"],))
            cur.execute(\"\"\"
                SELECT m.*, c.name AS category_name 
                FROM meat_items m
                LEFT JOIN categories c ON m.category_id = c.id
                WHERE m.shop_id = ?
                ORDER BY c.name, m.name
            \"\"\", (g.shop["id"],))
        else:
            cur.execute("SELECT * FROM categories ORDER BY name ASC")
            cur.execute(\"\"\"
                SELECT m.*, c.name AS category_name 
                FROM meat_items m
                LEFT JOIN categories c ON m.category_id = c.id
                ORDER BY c.name, m.name
            \"\"\")
        categories = cur.fetchall() # Note categories fetchall gets overridden by meat_items fetchall in original if not careful, wait! Let's do it safer.
"""
    # Wait, in the original code, the fetched `categories` is assigned before `meat_items` fetchall. Let's do a direct replace.
    new_sale_cat_new_fixed = """        # Fetch categories
        if g.shop:
            cur.execute("SELECT * FROM categories WHERE shop_id = ? ORDER BY name ASC", (g.shop["id"],))
        else:
            cur.execute("SELECT * FROM categories ORDER BY name ASC")
        categories = cur.fetchall()

        # Fetch all meat items with category name
        if g.shop:
            cur.execute(\"\"\"
                SELECT m.*, c.name AS category_name 
                FROM meat_items m
                LEFT JOIN categories c ON m.category_id = c.id
                WHERE m.shop_id = ?
                ORDER BY c.name, m.name
            \"\"\", (g.shop["id"],))
        else:
            cur.execute(\"\"\"
                SELECT m.*, c.name AS category_name 
                FROM meat_items m
                LEFT JOIN categories c ON m.category_id = c.id
                ORDER BY c.name, m.name
            \"\"\")"""
    content = content.replace(new_sale_cat_old, new_sale_cat_new_fixed)

    new_sale_insert_old = """                cur.execute(
                    \"\"\"
                    INSERT INTO sales (sale_datetime, user_id, customer_name, total_amount)
                    VALUES (?, ?, ?, ?)
                    \"\"\",
                    (now_iso, g.user["id"], customer_name or None, total_amount),
                )"""
    new_sale_insert_new = """                cur.execute(
                    \"\"\"
                    INSERT INTO sales (shop_id, sale_datetime, user_id, customer_name, total_amount)
                    VALUES (?, ?, ?, ?, ?)
                    \"\"\",
                    (g.shop["id"] if g.shop else None, now_iso, g.user["id"], customer_name or None, total_amount),
                )"""
    content = content.replace(new_sale_insert_old, new_sale_insert_new)

    # Patches for sale_receipt
    receipt_old = """        cur.execute(
            \"\"\"
            SELECT s.*, u.username
            FROM sales s
            JOIN users u ON s.user_id = u.id
            WHERE s.id = ?
            \"\"\",
            (sale_id,),
        )"""
    receipt_new = """        if g.shop:
            cur.execute(
                \"\"\"
                SELECT s.*, u.username
                FROM sales s
                JOIN users u ON s.user_id = u.id
                WHERE s.id = ? AND s.shop_id = ?
                \"\"\",
                (sale_id, g.shop["id"]),
            )
        else:
            cur.execute(
                \"\"\"
                SELECT s.*, u.username
                FROM sales s
                JOIN users u ON s.user_id = u.id
                WHERE s.id = ?
                \"\"\",
                (sale_id,),
            )"""
    content = content.replace(receipt_old, receipt_new)

    # Patches for reports
    report_summary_old = """        cur.execute(
            \"\"\"
            SELECT
                DATE(sale_datetime) AS sale_date,
                COUNT(*) AS num_sales,
                SUM(total_amount) AS total_sales
            FROM sales
            WHERE sale_datetime BETWEEN ? AND ?
            GROUP BY DATE(sale_datetime)
            ORDER BY sale_date ASC
            \"\"\",
            (start_dt.isoformat(), end_dt.isoformat()),
        )"""
    report_summary_new = """        if g.shop:
            cur.execute(
                \"\"\"
                SELECT
                    DATE(sale_datetime) AS sale_date,
                    COUNT(*) AS num_sales,
                    SUM(total_amount) AS total_sales
                FROM sales
                WHERE shop_id = ? AND sale_datetime BETWEEN ? AND ?
                GROUP BY DATE(sale_datetime)
                ORDER BY sale_date ASC
                \"\"\",
                (g.shop["id"], start_dt.isoformat(), end_dt.isoformat()),
            )
        else:
            cur.execute(
                \"\"\"
                SELECT
                    DATE(sale_datetime) AS sale_date,
                    COUNT(*) AS num_sales,
                    SUM(total_amount) AS total_sales
                FROM sales
                WHERE sale_datetime BETWEEN ? AND ?
                GROUP BY DATE(sale_datetime)
                ORDER BY sale_date ASC
                \"\"\",
                (start_dt.isoformat(), end_dt.isoformat()),
            )"""
    content = content.replace(report_summary_old, report_summary_new)

    report_by_item_old = """        cur.execute(
            \"\"\"
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
            \"\"\",
            (start_dt.isoformat(), end_dt.isoformat()),
        )"""
    report_by_item_new = """        if g.shop:
            cur.execute(
                \"\"\"
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
                \"\"\",
                (g.shop["id"], start_dt.isoformat(), end_dt.isoformat()),
            )
        else:
            cur.execute(
                \"\"\"
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
                \"\"\",
                (start_dt.isoformat(), end_dt.isoformat()),
            )"""
    content = content.replace(report_by_item_old, report_by_item_new)

    with open("app.py", "w") as f:
        f.write(content)

if __name__ == "__main__":
    patch_routes_2()
