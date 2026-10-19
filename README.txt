MARTYR FRAGRANCES — DEMO POS
========================================
Premium storefront + admin point-of-sale project using Python, Flask, SQLite,
Jinja2, HTML, CSS, and a little plain JavaScript.

RUN LOCALLY
-----------
1. Install Python 3.10+.
2. Open this folder in a terminal.
3. Install dependencies:
       python -m pip install -r requirements.txt
4. Start the application:
       python app.py
5. Open http://127.0.0.1:8080

ADMIN ACCESS (PROJECT DEMO ONLY)
--------------------------------
Go to http://127.0.0.1:8080/admin/login
Username: admin
Password: martyr

The login page intentionally does not display the demo credentials. The
initial password is stored as a salted hash in the initialized SQLite file.
Older database files with legacy SHA-256 hashes are upgraded on next login.

IMPORTANT: DEMONSTRATION SYSTEM, NOT REAL COMMERCE
--------------------------------------------------
The storefront and POS deliberately accept Cash / GCash / Card as DEMO
payment methods. No payment gateway is connected; no actual payments are
collected, checked, or verified. Receipt pages state this clearly.
This is not production billing software.

FILES AND FEATURES
------------------
app.py           Routes, login, forms, stock and sale transaction logic.
db.py            SQLite connection, initialization, and old-data migrations.
schema.sql       Tables and constraints.
seed.sql         Default demo products, admin, initial sale and reviews.
templates/       Storefront and redesigned admin interface.
static/style.css Black/cream/gold brand design and responsive layouts.
static/site.js   Hero slides, searchable catalog, payment / register previews.
static/brand/    Original Martyr assets and cleaned transparent bottle photos.

Storefront
- Home feature carousel, product catalog, search and stock filters.
- Product details, stock-aware cart, demo checkout, printable receipt.

Admin
- Dashboard, MULTI-ITEM register, product editor, stock adjustments.
- Sales, expenses, reports and inventory movement history.
- Stock adjustments through the product editor are logged automatically.
- Reports subtract cost of goods sold AND operating expenses. Unit cost is
  snapshotted on new sales; migrated old sales use an estimated current cost.

SALE TRANSACTION
----------------
Both checkout and in-store register call save_sale(). The function obtains a
SQLite BEGIN IMMEDIATE write lock, reloads stock, checks availability,
records the sale and its per-item cost, conditionally deducts stock, writes
history, then commits all changes together. On failure it rolls back.

CONFIGURATION / SAFETY
----------------------
- Set MARTYR_SECRET_KEY as an environment variable if you need browser
  sessions to persist across server restarts. Otherwise the application
  creates a fresh random key at each startup (fine for a local demo).
- Form POST requests include CSRF tokens, including logout.
- Product image uploads allow JPG/PNG/WEBP/GIF files up to 5 MB, check file
  signatures and use randomized names (not user-controlled paths).
- Passwords are salted hashes for newly initialized databases.
- The public source-code download route and all download links were removed.
- SQLite runs with foreign-key checks and a 15-second busy timeout.
- Restarting the program DOES NOT wipe existing data in martyr.db.
  Make a copy of martyr.db before resetting or replacing the database.

TESTS
-----
Once dependencies are installed, from the project directory run:
       python -m unittest discover -s tests -v

The app will automatically create martyr.db on first run if it is missing.
To start from a fresh demo dataset, stop the app, back up martyr.db, and then
remove it before restarting.

CUSTOMER ACCOUNTS + TWO CHECKOUT FLOWS (OCT 2026)
-------------------------------------------------
- /account/register creates a customer profile with name/email/password;
  passwords are stored as salted hashes, never plaintext.
- /account/login and /account/logout manage CUSTOMER identity only.
- /account shows editable display name and purchases placed while signed in.
- Staff/admin login remains SEPARATE at /admin/login, with original demo
  credentials. Customer accounts cannot open the administrative register.
- 'Add to bag' puts the product in the regular cart. Bag checkout purchases
  the contents of the bag and clears it after a successful demo sale.
- 'Buy now / Checkout' opens a distinct direct-checkout session containing
  only the chosen item. Its sale does NOT clear or modify the shopping bag.
- Visitors can check out as guests; guests will not get saved account orders.
- If asked to sign in from checkout, the account page returns to checkout.
- Both flows still use the same stock-safe sale transaction code. Cash,
  GCash, and Card are simulated for classroom demonstration only.
- Existing installations auto-migrate the sales table to add customer_id.
  Existing sales remain unassigned (they cannot safely be linked retroactively).
- No source-code download route or cards are included.

IMAGE PRESENTATION / UI
-----------------------
- Bundled fragrance bottles now use static/brand/refined cutouts rebuilt
  directly from the original source assets with soft, clean transparency.
  This removes the blocky silver/white edge artifacts from the previous
  enlarged clean/display versions. Original brand source files are preserved.
  Existing bundled demo product references automatically migrate to refined
  paths on next startup. Uploaded/custom images are never overwritten.
- Card layout, spacing, detail shots, purchase actions, checkout, and account
  pages share the original black/cream/gold style and responsive design.
- Collections remains the original responsive GRID (not a carousel).
- Reviews keeps its smooth auto-scrolling carousel and accessible controls.
- Source product photos are limited in native detail. For true photo-sharp
  zoom, replace them with higher resolution originals using Admin > Products.

QA
--
From the project folder after installing requirements.txt:
    python -m unittest discover -s tests -v

Includes tests for account isolation, duplicate registration, buy-now/cart
independence, customer order history, and original POS transactions.
