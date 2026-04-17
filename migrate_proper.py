import sqlite3
import os

DB_PATH = 'butcher_shop.db'

def migrate_all():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("BEGIN TRANSACTION;")

    # 1. Create shops
    cur.execute('''
        CREATE TABLE IF NOT EXISTS shops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT 'Prime Cuts'
        )
    ''')

    cur.execute("SELECT COUNT(*) as c FROM shops")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO shops (name) VALUES ('Prime Cuts')")
    
    cur.execute("SELECT id FROM shops ORDER BY id LIMIT 1")
    default_shop_id = cur.fetchone()[0]

    # 2. Add shop_id to missing tables
    tables = ['categories', 'meat_items', 'sales']
    for table in tables:
        # Check if shop_id exists
        cur.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cur.fetchall()]
        if 'shop_id' not in columns:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN shop_id INTEGER REFERENCES shops(id)")
            cur.execute(f"UPDATE {table} SET shop_id = ?", (default_shop_id,))

    # 3. Handle users table
    cur.execute("PRAGMA table_info(users)")
    user_columns = [row[1] for row in cur.fetchall()]
    if 'shop_id' not in user_columns:
        cur.execute("""
            CREATE TABLE users_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shop_id INTEGER REFERENCES shops(id),
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('superadmin', 'admin', 'cashier'))
            )
        """)
        
        cur.execute("""
            INSERT INTO users_new (id, shop_id, username, password_hash, role)
            SELECT id, ?, username, password_hash, role FROM users
        """, (default_shop_id,))
        
        cur.execute("DROP TABLE users")
        cur.execute("ALTER TABLE users_new RENAME TO users")

    # 4. Add superadmin
    cur.execute("SELECT COUNT(*) as c FROM users WHERE role = 'superadmin'")
    if cur.fetchone()[0] == 0:
        from werkzeug.security import generate_password_hash
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("superadmin", generate_password_hash("superadmin123"), "superadmin"),
        )
        # superadmin has no shop_id (NULL)

    conn.commit()
    conn.close()
    print("Migration successful")

if __name__ == '__main__':
    migrate_all()
