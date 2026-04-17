import re

def patch_app():
    with open("app.py", "r") as f:
        content = f.read()

    # 1. Update init_db schema
    content = content.replace("CREATE TABLE IF NOT EXISTS users (", "CREATE TABLE IF NOT EXISTS shops (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            name TEXT NOT NULL DEFAULT 'Prime Cuts'\n        )\n        \"\"\"\n    )\n    cur.execute(\n        \"\"\"\n        CREATE TABLE IF NOT EXISTS users (")
    
    # Update all tables to have shop_id
    content = content.replace("username TEXT UNIQUE NOT NULL,\n            password_hash TEXT NOT NULL,\n            role TEXT NOT NULL CHECK(role IN ('admin', 'cashier'))", "shop_id INTEGER REFERENCES shops(id),\n            username TEXT UNIQUE NOT NULL,\n            password_hash TEXT NOT NULL,\n            role TEXT NOT NULL CHECK(role IN ('superadmin', 'admin', 'cashier'))")
    content = content.replace("name TEXT UNIQUE NOT NULL", "shop_id INTEGER REFERENCES shops(id),\n            name TEXT NOT NULL")
    # For categories, 'name' should be unique per shop, so UNIQUE(shop_id, name). But we can just make it unique with a constraint.
    content = content.replace("name TEXT UNIQUE NOT NULL", "shop_id INTEGER REFERENCES shops(id),\n            name TEXT NOT NULL,\n            UNIQUE(shop_id, name)")
    
    # meat_items
    content = content.replace("category_id INTEGER,", "shop_id INTEGER REFERENCES shops(id),\n            category_id INTEGER,")
    
    # sales
    content = content.replace("sale_datetime TEXT NOT NULL,", "shop_id INTEGER REFERENCES shops(id),\n            sale_datetime TEXT NOT NULL,")

    # 2. Update ensure_default_admin to create superadmin
    superadmin_code = """
    # Check for superadmin
    cur.execute("SELECT COUNT(*) AS c FROM users WHERE role = 'superadmin'")
    if cur.fetchone()["c"] == 0:
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("superadmin", generate_password_hash("superadmin123"), "superadmin"),
        )
    """
    content = content.replace("# Check for admin", superadmin_code + "\n    # Check for admin")

    # 3. Add load shop in before_request
    before_req = """
        user_id = session.get("user_id")
        if user_id is None:
            g.user = None
            g.shop = None
        else:
            g.user = get_user_by_id(user_id)
            if g.user and g.user["shop_id"]:
                conn = get_db()
                cur = conn.cursor()
                cur.execute("SELECT * FROM shops WHERE id = ?", (g.user["shop_id"],))
                g.shop = cur.fetchone()
                conn.close()
            else:
                g.shop = None
    """
    content = re.sub(r'user_id = session\.get\("user_id"\).*?else:\s*g\.user = get_user_by_id\(user_id\)', before_req, content, flags=re.DOTALL)

    # 4. Context processor for shop
    inject_now = """
    @app.context_processor
    def inject_shop():
        shop_name = g.shop["name"] if getattr(g, "shop", None) else "Prime Cuts POS"
        return {"current_year": datetime.now().year, "shop_name": shop_name}
    """
    content = re.sub(r'@app\.context_processor.*?\n\s+return \{"current_year": datetime\.now\(\)\.year\}', inject_now, content, flags=re.DOTALL)

    with open("app.py", "w") as f:
        f.write(content)

if __name__ == '__main__':
    patch_app()
