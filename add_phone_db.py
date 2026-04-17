import sqlite3

def add_phone():
    conn = sqlite3.connect("butcher_shop.db")
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(shops)")
    cols = [r[1] for r in cur.fetchall()]
    if "phone_number" not in cols:
        cur.execute("ALTER TABLE shops ADD COLUMN phone_number TEXT DEFAULT ''")
        conn.commit()
    conn.close()
    print("Added phone_number to shops table.")

if __name__ == "__main__":
    add_phone()
