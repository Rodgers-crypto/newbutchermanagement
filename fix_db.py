import sqlite3
import os

DB_PATH = 'butcher_shop.db'

def migrate_users_table():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("BEGIN TRANSACTION;")

    # 1. Create new table without the strict CHECK constraint (or with superadmin included)
    cur.execute("""
        CREATE TABLE users_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER REFERENCES shops(id),
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('superadmin', 'admin', 'cashier'))
        )
    """)

    # 2. Copy data
    cur.execute("""
        INSERT INTO users_new (id, shop_id, username, password_hash, role)
        SELECT id, shop_id, username, password_hash, role FROM users
    """)

    # 3. Drop old table
    cur.execute("DROP TABLE users")

    # 4. Rename new to old
    cur.execute("ALTER TABLE users_new RENAME TO users")

    # 5. Add superadmin
    from werkzeug.security import generate_password_hash
    cur.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        ("superadmin", generate_password_hash("superadmin123"), "superadmin"),
    )

    conn.commit()
    conn.close()
    print("User table migrated and superadmin added.")

if __name__ == '__main__':
    migrate_users_table()
