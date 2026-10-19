"""Martyr Fragrances — storefront and demo point of sale.

The routes stay intentionally small and use ordinary SQL. Both the shop checkout
and the in-store register call save_sale so stock/history behave consistently.
"""

import hashlib
import hmac
import math
import os
import re
import secrets
import sqlite3
import uuid
from datetime import date
from functools import wraps
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db, init_db

app = Flask(__name__, static_folder="static", static_url_path="")
# A new random key is fine for local demos; set MARTYR_SECRET_KEY to keep sessions
# across server restarts when deploying the demo to a shared computer.
app.secret_key = os.environ.get("MARTYR_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    MAX_CONTENT_LENGTH=6 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

HEROES = ["unreleased-1", "escobar", "midnight-blaze", "el-patron"]
PAYMENTS = ("Cash", "GCash", "Card")
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def peso(amount):
    return f"₱{float(amount or 0):,.2f}"


app.jinja_env.filters["peso"] = peso


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "product"


def csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)
    return session["_csrf_token"]


@app.before_request
def check_csrf():
    if request.method == "POST":
        submitted = request.form.get("_csrf_token", "")
        if not hmac.compare_digest(submitted, csrf_token()):
            abort(400, description="Form expired. Refresh the page and try again.")


def cart_count():
    return sum(max(0, int(q)) for q in session.get("cart", {}).values())


@app.context_processor
def inject_nav():
    return {
        "cart_count": cart_count(),
        "admin_name": session.get("user"),
        "customer_name": session.get("customer_name"),
        "customer_id": session.get("customer_id"),
        "csrf_token": csrf_token,
        "today": date.today().isoformat(),
    }


def require_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)

    return wrapped


def require_customer(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("customer_id"):
            flash("Sign in to view your customer account.")
            return redirect(url_for("customer_login"))
        return view(*args, **kwargs)
    return wrapped


def customer_by_id(connection, customer_id):
    return connection.execute("SELECT id, full_name, email, created_at FROM customer_accounts WHERE id = ?",
                              (customer_id,)).fetchone()


def checked_checkout_mode(value):
    return "now" if value == "now" else "bag"


def checkout_lines(connection, mode):
    if mode != "now":
        return cart_lines(connection)
    instant = session.get("instant_checkout", {})
    product = product_by_id(connection, instant.get("product_id", ""))
    qty = instant.get("qty", 0)
    return [(product, int(qty))] if product and isinstance(qty, int) and qty > 0 else []


def safe_customer_return(value):
    # Allow only internal checkout continuation URLs. Never arbitrary redirects.
    return value if value in ("/checkout", "/checkout?mode=now") else None


def customer_email(value):
    email = value.strip().lower()
    if len(email) > 160 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Enter a valid email address.")
    return email


def product_by_id(connection, product_id):
    return connection.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()


def cart_lines(connection):
    lines = []
    for product_id, quantity in session.get("cart", {}).items():
        product = product_by_id(connection, product_id)
        qty = int(quantity)
        if product and qty > 0:
            lines.append((product, qty))
    return lines


def next_sale_number(connection):
    """Called only while holding SQLite's BEGIN IMMEDIATE write lock."""
    next_id = connection.execute("SELECT COALESCE(MAX(id), 0) + 1 AS n FROM sales").fetchone()["n"]
    return f"MF-{2400 + next_id}"


def safe_number(value, label, *, minimum=0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Enter a valid {label.lower()}.") from None
    if not math.isfinite(number) or number < minimum:
        raise ValueError(f"{label} must be at least {minimum:g}.")
    return round(number, 2)


def safe_integer(value, label, *, minimum=0):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Enter a valid {label.lower()}.") from None
    if number < minimum:
        raise ValueError(f"{label} must be at least {minimum}.")
    return number


def save_sale(connection, lines, channel, payment, customer, tendered, customer_id=None):
    """Atomically record sale, snapshot cost, deduct stock, and write history.

    Reload every product *after* acquiring the SQLite write lock. That way even
    two people submitting at once cannot sell the same last bottle.
    """
    if not lines:
        return None, "Add a product before saving the sale."
    if payment not in PAYMENTS:
        return None, "Choose a valid payment method."

    combined = {}
    try:
        for product, quantity in lines:
            if product is None:
                return None, "One of the selected products is unavailable."
            qty = safe_integer(quantity, "Quantity", minimum=1)
            product_id = product["id"]
            combined[product_id] = combined.get(product_id, 0) + qty
    except ValueError as error:
        return None, str(error)

    try:
        connection.execute("BEGIN IMMEDIATE")
        fresh_lines = []
        for product_id, qty in combined.items():
            product = product_by_id(connection, product_id)
            if product is None:
                connection.rollback()
                return None, "A product is no longer available."
            if qty > product["stock"]:
                connection.rollback()
                return None, f"Only {product['stock']} left of {product['name']}."
            fresh_lines.append((product, qty))

        subtotal = round(sum(p["price"] * q for p, q in fresh_lines), 2)
        if payment == "Cash":
            if tendered is None or not math.isfinite(tendered) or tendered < subtotal:
                connection.rollback()
                return None, "Cash received is less than the total."
            change = round(tendered - subtotal, 2)
        else:
            tendered, change = subtotal, 0

        number = next_sale_number(connection)
        cursor = connection.execute(
            """
            INSERT INTO sales (sale_number, sold_at, channel, payment_method,
                               customer_name, subtotal, total, tendered, change_amount, customer_id)
            VALUES (?, datetime('now', 'localtime'), ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (number, channel, payment, (customer or "").strip()[:100] or "Walk-in",
             subtotal, subtotal, tendered, change, customer_id),
        )
        sale_id = cursor.lastrowid
        for product, qty in fresh_lines:
            connection.execute(
                """INSERT INTO sale_items
                   (sale_id, product_id, product_name, quantity, unit_price, unit_cost, line_total)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (sale_id, product["id"], product["name"], qty,
                 product["price"], product["cost_price"], round(product["price"] * qty, 2)),
            )
            updated = connection.execute(
                "UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= ?",
                (qty, product["id"], qty),
            )
            if updated.rowcount != 1:
                connection.rollback()
                return None, f"Stock changed for {product['name']}. Please retry."
            connection.execute(
                """INSERT INTO inventory_history
                   (product_id, product_name, change_qty, reason, note, created_at)
                   VALUES (?, ?, ?, 'sale', ?, datetime('now', 'localtime'))""",
                (product["id"], product["name"], -qty, number),
            )
        connection.commit()
        return number, None
    except sqlite3.Error:
        connection.rollback()
        app.logger.exception("Unable to save sale")
        return None, "Could not save the sale. Please try again."


def read_payment():
    payment = request.form.get("payment", "Cash")
    if payment not in PAYMENTS:
        raise ValueError("Choose a valid payment method.")
    tendered = None
    if payment == "Cash":
        tendered = safe_number(request.form.get("tendered"), "Cash received")
    return payment, tendered


def store_image(file_storage):
    """Accept only small, real JPEG/PNG/WEBP/GIF uploads, never user filenames."""
    if not file_storage or not file_storage.filename:
        return None
    data = file_storage.stream.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Image must be smaller than 5 MB.")
    if data.startswith(b"\xff\xd8\xff"):
        extension = ".jpg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        extension = ".png"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        extension = ".webp"
    elif data.startswith((b"GIF87a", b"GIF89a")):
        extension = ".gif"
    else:
        raise ValueError("Upload a JPG, PNG, WEBP, or GIF image.")
    folder = Path(app.static_folder) / "uploads"
    folder.mkdir(exist_ok=True)
    filename = uuid.uuid4().hex + extension
    (folder / filename).write_bytes(data)
    return f"/uploads/{filename}"


@app.get("/")
def home():
    connection = get_db()
    products = [product_by_id(connection, hero_id) for hero_id in HEROES]
    connection.close()
    return render_template("home.html", products=[p for p in products if p], dark=True)


@app.get("/collections")
def collections():
    connection = get_db()
    products = connection.execute("SELECT * FROM products ORDER BY name").fetchall()
    connection.close()
    return render_template("collections.html", products=products)


@app.get("/product/<product_id>")
def product_page(product_id):
    connection = get_db()
    product = product_by_id(connection, product_id)
    if product is None:
        connection.close()
        return render_template("missing.html"), 404
    accords = connection.execute(
        "SELECT name, level FROM product_accords WHERE product_id = ? ORDER BY level DESC",
        (product_id,),
    ).fetchall()
    related = connection.execute(
        "SELECT * FROM products WHERE id != ? ORDER BY stock > 0 DESC, name LIMIT 3",
        (product_id,),
    ).fetchall()
    connection.close()
    return render_template("product.html", product=product, accords=accords, related=related)


@app.post("/cart/add")
def add_to_cart():
    product_id = request.form.get("product_id", "")
    try:
        qty = safe_integer(request.form.get("qty", 1), "Quantity", minimum=1)
    except ValueError as error:
        flash(str(error))
        return redirect(url_for("collections"))
    connection = get_db()
    product = product_by_id(connection, product_id)
    connection.close()
    if product is None:
        flash("That fragrance is no longer available.")
        return redirect(url_for("collections"))
    cart = dict(session.get("cart", {}))
    new_qty = int(cart.get(product_id, 0)) + qty
    if new_qty > product["stock"]:
        flash(f"Only {product['stock']} left of {product['name']}.")
        return redirect(url_for("product_page", product_id=product_id))
    cart[product_id] = new_qty
    session["cart"] = cart
    flash(f"{product['name']} added to your cart.")
    return redirect(url_for("cart"))


@app.post("/buy-now")
def buy_now():
    product_id = request.form.get("product_id", "")
    try:
        qty = safe_integer(request.form.get("qty", 1), "Quantity", minimum=1)
    except ValueError as error:
        flash(str(error))
        return redirect(url_for("collections"))
    connection = get_db()
    product = product_by_id(connection, product_id)
    connection.close()
    if product is None:
        flash("That fragrance is no longer available.")
        return redirect(url_for("collections"))
    if qty > product["stock"]:
        flash(f"Only {product['stock']} left of {product['name']}.")
        return redirect(url_for("product_page", product_id=product_id))
    session["instant_checkout"] = {"product_id": product_id, "qty": qty}
    return redirect(url_for("checkout", mode="now"))


@app.post("/cart/update")
def update_cart():
    product_id = request.form.get("product_id", "")
    try:
        qty = safe_integer(request.form.get("qty", 1), "Quantity")
    except ValueError as error:
        flash(str(error))
        return redirect(url_for("cart"))
    cart = dict(session.get("cart", {}))
    if qty == 0:
        cart.pop(product_id, None)
    else:
        connection = get_db()
        product = product_by_id(connection, product_id)
        connection.close()
        if product:
            cart[product_id] = min(qty, product["stock"])
            if cart[product_id] == 0:
                cart.pop(product_id, None)
        else:
            cart.pop(product_id, None)
    session["cart"] = cart
    return redirect(url_for("cart"))


@app.get("/cart")
def cart():
    connection = get_db()
    lines = cart_lines(connection)
    connection.close()
    total = round(sum(p["price"] * q for p, q in lines), 2)
    return render_template("cart.html", lines=lines, total=total)


@app.get("/checkout")
def checkout():
    mode = checked_checkout_mode(request.args.get("mode"))
    connection = get_db()
    lines = checkout_lines(connection, mode)
    customer = customer_by_id(connection, session["customer_id"]) if session.get("customer_id") else None
    connection.close()
    if not lines:
        flash("Your selected fragrance is no longer available." if mode == "now" else "Add a fragrance before checkout.")
        return redirect(url_for("cart" if mode == "bag" else "collections"))
    return render_template(
        "checkout.html", lines=lines, total=round(sum(p["price"] * q for p, q in lines), 2),
        payments=PAYMENTS, mode=mode, customer=customer,
    )


@app.post("/checkout")
def checkout_submit():
    mode = checked_checkout_mode(request.form.get("mode"))
    connection = get_db()
    lines = checkout_lines(connection, mode)
    account = customer_by_id(connection, session["customer_id"]) if session.get("customer_id") else None
    customer_id = account["id"] if account else None
    customer_name = account["full_name"] if account else request.form.get("customer_name", "")
    try:
        payment, tendered = read_payment()
        number, error = save_sale(connection, lines, "website", payment,
                                  customer_name, tendered, customer_id=customer_id)
    except ValueError as exc:
        number, error = None, str(exc)
    finally:
        connection.close()
    if error:
        flash(error)
        return redirect(url_for("checkout", **({"mode": "now"} if mode == "now" else {})))
    if mode == "now":
        session.pop("instant_checkout", None)
    else:
        session["cart"] = {}
    return redirect(url_for("receipt", sale_number=number))


@app.get("/receipt/<sale_number>")
def receipt(sale_number):
    connection = get_db()
    sale = connection.execute("SELECT * FROM sales WHERE sale_number = ?", (sale_number,)).fetchone()
    if sale is None:
        connection.close()
        return render_template("missing.html"), 404
    items = connection.execute("SELECT * FROM sale_items WHERE sale_id = ?", (sale["id"],)).fetchall()
    connection.close()
    return render_template("receipt.html", sale=sale, items=items)


@app.get("/reviews")
def reviews():
    connection = get_db()
    rows = connection.execute("SELECT * FROM reviews ORDER BY id").fetchall()
    connection.close()
    return render_template("reviews.html", reviews=rows)


@app.get("/about")
def about():
    return render_template("about.html")


@app.route("/account/register", methods=["GET", "POST"])
def customer_register():
    if session.get("customer_id"):
        return redirect(url_for("customer_account"))
    error = None
    if request.method == "POST":
        try:
            full_name = request.form.get("full_name", "").strip()
            email = customer_email(request.form.get("email", ""))
            password = request.form.get("password", "")
            confirmation = request.form.get("confirm_password", "")
            if not 2 <= len(full_name) <= 100:
                raise ValueError("Enter your full name (2–100 characters).")
            if len(password) < 8 or len(password) > 128:
                raise ValueError("Use a password of 8–128 characters.")
            if password != confirmation:
                raise ValueError("Passwords do not match.")
            connection = get_db()
            try:
                cursor = connection.execute(
                    "INSERT INTO customer_accounts (full_name,email,password_hash,created_at) "
                    "VALUES (?,?,?,datetime('now','localtime'))",
                    (full_name, email, generate_password_hash(password)),
                )
                connection.commit()
                session["customer_id"] = cursor.lastrowid
                session["customer_name"] = full_name
                flash("Welcome to the house. Your account is ready.")
                return redirect(safe_customer_return(request.form.get("next", "")) or url_for("customer_account"))
            except sqlite3.IntegrityError:
                error = "That email is already registered. Try signing in."
            finally:
                connection.close()
        except ValueError as exc:
            error = str(exc)
    return render_template("customer_register.html", error=error)


@app.route("/account/login", methods=["GET", "POST"])
def customer_login():
    if session.get("customer_id"):
        return redirect(url_for("customer_account"))
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        connection = get_db()
        account = connection.execute(
            "SELECT * FROM customer_accounts WHERE email = ?", (email,)
        ).fetchone()
        connection.close()
        if account and check_password_hash(account["password_hash"], password):
            session["customer_id"] = account["id"]
            session["customer_name"] = account["full_name"]
            flash("You are signed in.")
            return redirect(safe_customer_return(request.form.get("next", "")) or url_for("customer_account"))
        error = "Email or password is incorrect."
    return render_template("customer_login.html", error=error)


@app.post("/account/logout")
@require_customer
def customer_logout():
    # Preserve the browsing bag while removing customer-only identity.
    session.pop("customer_id", None)
    session.pop("customer_name", None)
    flash("You have signed out of your account.")
    return redirect(url_for("home"))


@app.get("/account")
@require_customer
def customer_account():
    connection = get_db()
    account = customer_by_id(connection, session["customer_id"])
    if account is None:
        connection.close()
        session.pop("customer_id", None)
        session.pop("customer_name", None)
        return redirect(url_for("customer_login"))
    orders = connection.execute(
        "SELECT * FROM sales WHERE customer_id = ? ORDER BY id DESC", (account["id"],)
    ).fetchall()
    connection.close()
    return render_template("customer_account.html", account=account, orders=orders)


@app.post("/account/profile")
@require_customer
def customer_profile_update():
    full_name = request.form.get("full_name", "").strip()
    if not 2 <= len(full_name) <= 100:
        flash("Enter your full name (2–100 characters).")
        return redirect(url_for("customer_account"))
    connection = get_db()
    connection.execute("UPDATE customer_accounts SET full_name=? WHERE id=?",
                       (full_name, session["customer_id"]))
    connection.commit()
    connection.close()
    session["customer_name"] = full_name
    flash("Your account details were updated.")
    return redirect(url_for("customer_account"))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        connection = get_db()
        user = connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user:
            stored = user["password_hash"]
            modern = stored.startswith(("scrypt:", "pbkdf2:"))
            accepted = check_password_hash(stored, password) if modern else (
                hmac.compare_digest(stored, hashlib.sha256(password.encode()).hexdigest())
            )
        else:
            accepted = False
        if accepted:
            if not modern:
                connection.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                                   (generate_password_hash(password), user["id"]))
                connection.commit()
            connection.close()
            session.clear()
            session["user"] = user["full_name"]
            return redirect(url_for("admin_home"))
        connection.close()
        error = "Username or password is incorrect."
    return render_template("admin_login.html", error=error)


@app.post("/admin/logout")
@require_admin
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.get("/admin")
@require_admin
def admin_home():
    connection = get_db()
    sales_total = connection.execute("SELECT COALESCE(SUM(total), 0) AS n FROM sales").fetchone()["n"]
    expense_total = connection.execute("SELECT COALESCE(SUM(amount), 0) AS n FROM expenses").fetchone()["n"]
    cost_of_goods = connection.execute(
        "SELECT COALESCE(SUM(quantity * unit_cost), 0) AS n FROM sale_items"
    ).fetchone()["n"]
    sale_count = connection.execute("SELECT COUNT(*) AS n FROM sales").fetchone()["n"]
    product_count = connection.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"]
    low_stock = connection.execute(
        "SELECT * FROM products WHERE stock <= reorder_level ORDER BY stock, name"
    ).fetchall()
    recent = connection.execute("SELECT * FROM sales ORDER BY id DESC LIMIT 6").fetchall()
    connection.close()
    return render_template("admin_home.html", sales_total=sales_total,
                           expense_total=expense_total, cost_of_goods=cost_of_goods,
                           product_count=product_count, sale_count=sale_count,
                           low_stock=low_stock, recent=recent)


@app.route("/admin/products", methods=["GET", "POST"])
@require_admin
def admin_products():
    connection = get_db()
    if request.method == "POST":
        editing_id = request.form.get("id", "").strip()
        try:
            name = request.form.get("name", "").strip()
            if not name:
                raise ValueError("Enter a product name.")
            price = safe_number(request.form.get("price"), "Price", minimum=0.01)
            cost_price = safe_number(request.form.get("cost_price"), "Unit cost")
            stock = safe_integer(request.form.get("stock"), "Stock")
            reorder_level = safe_integer(request.form.get("reorder_level"), "Reorder level")
            size = request.form.get("size_label", "").strip()[:40] or "50 mL"
            description = request.form.get("description", "").strip()
            if not description:
                raise ValueError("Enter a product description.")
            image = store_image(request.files.get("image"))
            # Lock before reading existing stock or allocating a new slug.
            # Otherwise a concurrent sale could be overwritten by an editor save.
            connection.execute("BEGIN IMMEDIATE")
            if editing_id:
                product_id = editing_id
                existing = product_by_id(connection, product_id)
                if not existing:
                    raise ValueError("That product no longer exists.")
            else:
                base = slugify(name)
                product_id = base
                index = 2
                while product_by_id(connection, product_id):
                    product_id = f"{base}-{index}"
                    index += 1
                existing = None
            fields = (name, price, cost_price, stock, reorder_level, size,
                      description, description[:80])
            if existing:
                image = image or existing["image"]
                connection.execute(
                    """UPDATE products SET name=?, price=?, cost_price=?, stock=?,
                       reorder_level=?, size_label=?, description=?, blurb=?, image=?
                       WHERE id=?""",
                    (*fields, image, product_id),
                )
                stock_change = stock - existing["stock"]
                reason = "stock-adjustment"
            else:
                connection.execute(
                    """INSERT INTO products
                       (name,price,cost_price,stock,reorder_level,size_label,description,
                        blurb,image,id,season,longevity,rating)
                       VALUES (?,?,?,?,?,?,?,?,?,?,'All year','6–8 hours',5)""",
                    (*fields, image, product_id),
                )
                stock_change = stock
                reason = "opening-stock"
            if stock_change:
                connection.execute(
                    """INSERT INTO inventory_history
                       (product_id,product_name,change_qty,reason,note,created_at)
                       VALUES (?,?,?,?,?,datetime('now','localtime'))""",
                    (product_id, name, stock_change, reason, "Product editor"),
                )
            connection.commit()
            flash("Product saved. Inventory history updated." if stock_change else "Product saved.")
            connection.close()
            return redirect(url_for("admin_products"))
        except ValueError as error:
            connection.rollback()
            flash(str(error))
    editing = product_by_id(connection, request.args["edit"]) if request.args.get("edit") else None
    products = connection.execute("SELECT * FROM products ORDER BY name").fetchall()
    connection.close()
    return render_template("admin_products.html", products=products, editing=editing)


@app.post("/admin/stock")
@require_admin
def admin_stock_submit():
    try:
        qty = safe_integer(request.form.get("qty"), "Quantity", minimum=1)
        direction = request.form.get("direction", "in")
        if direction not in ("in", "out"):
            raise ValueError("Choose stock in or stock out.")
    except ValueError as error:
        flash(str(error))
        return redirect(url_for("admin_stock"))
    product_id = request.form.get("product_id", "")
    note = request.form.get("note", "").strip()[:200] or "Manual count"
    change = qty if direction == "in" else -qty
    connection = get_db()
    try:
        connection.execute("BEGIN IMMEDIATE")
        product = product_by_id(connection, product_id)
        if product is None:
            flash("Choose an existing product.")
        elif product["stock"] + change < 0:
            flash("That would take stock below zero.")
        else:
            connection.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (change, product_id))
            connection.execute(
                """INSERT INTO inventory_history
                   (product_id, product_name, change_qty, reason, note, created_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))""",
                (product_id, product["name"], change, "stock-in" if change > 0 else "stock-out", note),
            )
            connection.commit()
            flash("Stock updated and logged.")
    finally:
        connection.close()
    return redirect(url_for("admin_stock"))


@app.get("/admin/stock")
@require_admin
def admin_stock():
    connection = get_db()
    products = connection.execute("SELECT * FROM products ORDER BY name").fetchall()
    connection.close()
    return render_template("admin_stock.html", products=products)


@app.route("/admin/register", methods=["GET", "POST"])
@require_admin
def admin_register():
    connection = get_db()
    error = None
    if request.method == "POST":
        try:
            product_ids = request.form.getlist("product_id[]") or request.form.getlist("product_id")
            quantities = request.form.getlist("qty[]") or request.form.getlist("qty")
            if len(product_ids) != len(quantities) or not product_ids:
                raise ValueError("Add at least one product to the sale.")
            lines = [(product_by_id(connection, pid), safe_integer(qty, "Quantity", minimum=1))
                     for pid, qty in zip(product_ids, quantities)]
            payment, tendered = read_payment()
            number, error = save_sale(connection, lines, "in-store", payment,
                                      request.form.get("customer_name", ""), tendered)
            if number:
                connection.close()
                return redirect(url_for("receipt", sale_number=number))
        except ValueError as exc:
            error = str(exc)
    products = connection.execute("SELECT * FROM products WHERE stock > 0 ORDER BY name").fetchall()
    connection.close()
    return render_template("admin_register.html", products=products, payments=PAYMENTS, error=error)


@app.get("/admin/sales")
@require_admin
def admin_sales():
    connection = get_db()
    sales = connection.execute("SELECT * FROM sales ORDER BY id DESC").fetchall()
    items = connection.execute("SELECT * FROM sale_items ORDER BY id").fetchall()
    connection.close()
    grouped = {}
    for item in items:
        grouped.setdefault(item["sale_id"], []).append(item)
    return render_template("admin_sales.html", sales=sales, grouped=grouped)


@app.route("/admin/expenses", methods=["GET", "POST"])
@require_admin
def admin_expenses():
    connection = get_db()
    if request.method == "POST":
        try:
            spent_on = request.form.get("spent_on", "")
            date.fromisoformat(spent_on)
            amount = safe_number(request.form.get("amount"), "Amount", minimum=0.01)
            category = request.form.get("category", "").strip()[:80]
            if not category:
                raise ValueError("Enter an expense category.")
            connection.execute(
                "INSERT INTO expenses (spent_on, category, amount, note) VALUES (?, ?, ?, ?)",
                (spent_on, category, amount, request.form.get("note", "").strip()[:300]),
            )
            connection.commit()
            flash("Expense saved.")
            connection.close()
            return redirect(url_for("admin_expenses"))
        except ValueError:
            flash("Enter a valid date, category, and positive amount.")
    rows = connection.execute("SELECT * FROM expenses ORDER BY spent_on DESC, id DESC").fetchall()
    connection.close()
    return render_template("admin_expenses.html", expenses=rows)


@app.get("/admin/reports")
@require_admin
def admin_reports():
    connection = get_db()
    sellers = connection.execute(
        """SELECT product_name, SUM(quantity) AS qty, SUM(line_total) AS sales,
                  SUM(quantity * unit_cost) AS cogs
           FROM sale_items GROUP BY product_name ORDER BY sales DESC""",
    ).fetchall()
    revenue = connection.execute("SELECT COALESCE(SUM(total), 0) AS n FROM sales").fetchone()["n"]
    expenses = connection.execute("SELECT COALESCE(SUM(amount), 0) AS n FROM expenses").fetchone()["n"]
    cogs = connection.execute(
        "SELECT COALESCE(SUM(quantity * unit_cost), 0) AS n FROM sale_items"
    ).fetchone()["n"]
    connection.close()
    return render_template("admin_reports.html", sellers=sellers, revenue=revenue,
                           expenses=expenses, cogs=cogs)


@app.get("/admin/history")
@require_admin
def admin_history():
    connection = get_db()
    rows = connection.execute("SELECT * FROM inventory_history ORDER BY id DESC").fetchall()
    connection.close()
    return render_template("admin_history.html", rows=rows)


@app.errorhandler(404)
def missing(_error):
    return render_template("missing.html"), 404


@app.errorhandler(400)
def invalid_form(error):
    return render_template("missing.html", message=error.description), 400


@app.errorhandler(RequestEntityTooLarge)
def upload_too_large(_error):
    return render_template("missing.html", message="Uploaded file is too large (maximum 5 MB)."), 413


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8080, debug=False)
