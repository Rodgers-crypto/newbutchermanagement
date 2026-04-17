import sqlite3

def fix_categories():
    conn = sqlite3.connect("butcher_shop.db")
    cur = conn.cursor()
    cur.execute("BEGIN TRANSACTION;")
    cur.execute("""
        CREATE TABLE categories_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER REFERENCES shops(id),
            name TEXT NOT NULL
        )
    """)
    cur.execute("INSERT INTO categories_new (id, shop_id, name) SELECT id, shop_id, name FROM categories")
    cur.execute("DROP TABLE categories")
    cur.execute("ALTER TABLE categories_new RENAME TO categories")
    conn.commit()
    conn.close()
    print("Categories fixed")

if __name__ == "__main__":
    fix_categories()
