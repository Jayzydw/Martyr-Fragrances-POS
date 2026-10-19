"""Open the SQLite file; safely initialize and migrate older demo databases."""

import sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parent
DB_FILE = ROOT / "martyr.db"


def get_db():
    connection = sqlite3.connect(DB_FILE, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 15000")
    return connection


def init_db():
    connection = get_db()
    try:
        connection.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))
        columns = {column["name"] for column in connection.execute("PRAGMA table_info(sale_items)")}
        if "unit_cost" not in columns:
            # Legacy sales have no cost snapshot, so this is a best-effort estimate
            # using the product's current recorded unit cost at migration time.
            connection.execute("ALTER TABLE sale_items ADD COLUMN unit_cost REAL NOT NULL DEFAULT 0")
            connection.execute("""UPDATE sale_items SET unit_cost = COALESCE(
                (SELECT cost_price FROM products WHERE products.id = sale_items.product_id), 0)""")
        sale_columns = {column["name"] for column in connection.execute("PRAGMA table_info(sales)")}
        if "customer_id" not in sale_columns:
            connection.execute("ALTER TABLE sales ADD COLUMN customer_id INTEGER REFERENCES customer_accounts(id)")
        # Edge-refined bundled bottle images (never rewrite user uploads).
        # The new URL also prevents browsers from showing a cached old cutout.
        bundled_bottles = (
            "24-9819321a.webp",
            "24-bf49f503.webp",
            "25-14fc31e8.webp",
            "26-c10878dc.webp",
            "27-3094994e.webp",
            "28-b6e846fd.webp",
            "29-124a857e.webp",
            "30-73b2aa90.webp",
            "31-b1fa48ff.webp",
        )
        for filename in bundled_bottles:
            new_image = f"/brand/refined/{filename}"
            previous_images = (f"/brand/clean/{filename}",
                               f"/brand/display/{filename}",
                               f"/brand/refined/{filename}")
            connection.execute(
                "UPDATE products SET image = ? WHERE image IN (?, ?, ?)",
                (new_image, *previous_images),
            )
        already_seeded = connection.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        if not already_seeded:
            connection.executescript((ROOT / "seed.sql").read_text(encoding="utf-8"))
            connection.execute("UPDATE users SET password_hash = ? WHERE username = 'admin'",
                               (generate_password_hash("martyr"),))
        connection.commit()
    finally:
        connection.close()
