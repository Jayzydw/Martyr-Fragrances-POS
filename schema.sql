-- Martyr Fragrances
-- These are the tables the point of sale uses.
-- Open this file first when you explain the database.

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customer_accounts (
    id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    price REAL NOT NULL,
    cost_price REAL NOT NULL,
    stock INTEGER NOT NULL,
    reorder_level INTEGER NOT NULL,
    size_label TEXT NOT NULL,
    image TEXT,
    blurb TEXT NOT NULL,
    description TEXT NOT NULL,
    season TEXT NOT NULL,
    longevity TEXT NOT NULL,
    rating INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS product_accords (
    id INTEGER PRIMARY KEY,
    product_id TEXT NOT NULL,
    name TEXT NOT NULL,
    level INTEGER NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY,
    sale_number TEXT UNIQUE NOT NULL,
    sold_at TEXT NOT NULL,
    channel TEXT NOT NULL,
    payment_method TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    customer_id INTEGER REFERENCES customer_accounts(id),
    subtotal REAL NOT NULL,
    total REAL NOT NULL,
    tendered REAL,
    change_amount REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sale_items (
    id INTEGER PRIMARY KEY,
    sale_id INTEGER NOT NULL,
    product_id TEXT NOT NULL,
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    unit_cost REAL NOT NULL DEFAULT 0,
    line_total REAL NOT NULL,
    FOREIGN KEY (sale_id) REFERENCES sales(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS inventory_history (
    id INTEGER PRIMARY KEY,
    product_id TEXT NOT NULL,
    product_name TEXT NOT NULL,
    change_qty INTEGER NOT NULL,
    reason TEXT NOT NULL,
    note TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY,
    spent_on TEXT NOT NULL,
    category TEXT NOT NULL,
    amount REAL NOT NULL,
    note TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY,
    author_name TEXT NOT NULL,
    product_name TEXT NOT NULL,
    stars INTEGER NOT NULL,
    quote TEXT NOT NULL
);
