import sqlite3
import os

DB_PATH = 'butcher_shop.db'

def migrate():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Create shops table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS shops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT 'Prime Cuts'
        )
    ''')

    # Insert a default shop
    cur.execute("SELECT COUNT(*) as c FROM shops")
    if cur.fetchone()["c"] == 0:
        cur.execute("INSERT INTO shops (name) VALUES ('Prime Cuts')")
    
    cur.execute("SELECT id FROM shops ORDER BY id LIMIT 1")
    default_shop_id = cur.fetchone()["id"]

    # Alter tables to add shop_id
    tables = ['users', 'categories', 'meat_items', 'sales']
    for table in tables:
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN shop_id INTEGER REFERENCES shops(id)")
            cur.execute(f"UPDATE {table} SET shop_id = ?", (default_shop_id,))
        except sqlite3.OperationalError as e:
            if 'duplicate column name' not in str(e):
                print(f"Error altering {table}: {e}")

    # Add superadmin if not exists
    cur.execute("SELECT COUNT(*) as c FROM users WHERE role = 'superadmin'")
    if cur.fetchone()["c"] == 0:
        from werkzeug.security import generate_password_hash
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("superadmin", generate_password_hash("superadmin123"), "superadmin"),
        )
        # superadmin has no shop_id

    conn.commit()
    conn.close()
    print("Migration successful")

if __name__ == '__main__':
    migrate()
