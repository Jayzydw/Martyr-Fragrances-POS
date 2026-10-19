"""Run with: python -m unittest discover -s tests -v"""

import io
import tempfile
import unittest
from pathlib import Path

import db
from app import app


class MartyrPosTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._original_db = db.DB_FILE
        cls._tmp = tempfile.TemporaryDirectory()
        db.DB_FILE = Path(cls._tmp.name) / "demo.db"
        db.init_db()
        app.config.update(TESTING=True)

    @classmethod
    def tearDownClass(cls):
        db.DB_FILE = cls._original_db
        cls._tmp.cleanup()

    def setUp(self):
        self.client = app.test_client()

    def csrf(self, path="/admin/login"):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as s:
            return s["_csrf_token"]

    def login(self):
        token = self.csrf()
        response = self.client.post("/admin/login", data={
            "_csrf_token": token, "username": "admin", "password": "martyr",
        })
        self.assertEqual(response.status_code, 302)
        return self.csrf("/admin")

    def test_download_route_removed(self):
        self.assertEqual(self.client.get("/download").status_code, 404)

    def test_csrf_rejects_missing_token(self):
        self.assertEqual(self.client.post("/cart/add", data={"product_id": "escobar"}).status_code, 400)

    def test_storefront_pages(self):
        for path in ("/", "/collections", "/product/escobar", "/cart", "/reviews", "/about"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_multi_item_sale_stock_cogs_and_history(self):
        token = self.login()
        conn = db.get_db()
        before = {p["id"]: p["stock"] for p in conn.execute("SELECT id,stock FROM products")}
        conn.close()
        response = self.client.post("/admin/register", data={
            "_csrf_token": token, "product_id[]": ["escobar", "gentleman"],
            "qty[]": ["1", "2"], "payment": "GCash", "customer_name": "Demo purchaser",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("/receipt/MF-", response.headers["Location"])
        conn = db.get_db()
        self.assertEqual(conn.execute("SELECT stock FROM products WHERE id='escobar'").fetchone()[0], before["escobar"]-1)
        self.assertEqual(conn.execute("SELECT stock FROM products WHERE id='gentleman'").fetchone()[0], before["gentleman"]-2)
        sale_id = conn.execute("SELECT MAX(id) FROM sales").fetchone()[0]
        items = conn.execute("SELECT * FROM sale_items WHERE sale_id=?", (sale_id,)).fetchall()
        self.assertEqual(len(items), 2)
        self.assertEqual(sum(r["quantity"]*r["unit_cost"] for r in items), 120+2*115)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM inventory_history WHERE note = (SELECT sale_number FROM sales WHERE id=?)", (sale_id,)).fetchone()[0],2)
        conn.close()

    def test_insufficient_stock_rolls_back(self):
        token = self.login()
        conn = db.get_db()
        count = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
        conn.close()
        response = self.client.post("/admin/register", data={
            "_csrf_token": token, "product_id[]": ["el-patron"], "qty[]": ["999"],
            "payment": "Card",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Only", response.data)
        conn = db.get_db()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0], count)
        conn.close()

    def test_product_editor_stock_change_logged(self):
        token = self.login()
        conn = db.get_db()
        old = conn.execute("SELECT * FROM products WHERE id='gentleman'").fetchone()
        old_stock = old["stock"]
        conn.close()
        response = self.client.post("/admin/products", data={
            "_csrf_token": token, "id": "gentleman", "name": "Gentleman",
            "price": 299, "cost_price": 115, "stock": old_stock + 5,
            "reorder_level": 5, "size_label": "50 mL", "description": "A refined scent.",
        })
        self.assertEqual(response.status_code, 302)
        conn = db.get_db()
        history = conn.execute("SELECT * FROM inventory_history WHERE product_id='gentleman' ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(history["change_qty"], 5)
        self.assertEqual(history["reason"], "stock-adjustment")
        conn.close()

    def test_customer_registration_login_and_no_admin_privileges(self):
        token = self.csrf("/account/register")
        response = self.client.post("/account/register", data={
            "_csrf_token": token, "full_name": "Demo Customer",
            "email": "democustomer@example.com", "password": "demo-password-2026",
            "confirm_password": "demo-password-2026",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/account")
        self.assertEqual(self.client.get("/account").status_code, 200)
        # A customer cannot access staff administration.
        self.assertIn("/admin/login", self.client.get("/admin").headers["Location"])
        with self.client.session_transaction() as s:
            self.assertNotIn("user", s)
        token = self.csrf("/account")
        self.client.post("/account/logout", data={"_csrf_token": token})
        self.assertIn("/account/login", self.client.get("/account").headers["Location"])
        self.client.post("/account/login", data={
            "_csrf_token": token, "email": "democustomer@example.com",
            "password": "demo-password-2026",
        })
        self.assertEqual(self.client.get("/account").status_code, 200)

    def test_duplicate_customer_emails_cannot_register(self):
        token = self.csrf("/account/register")
        account = {"_csrf_token": token, "full_name": "Primary Customer",
                   "email": "duplicate@example.com", "password": "test-pass-2026",
                   "confirm_password": "test-pass-2026"}
        self.assertEqual(self.client.post("/account/register", data=account).status_code, 302)
        self.client.post("/account/logout", data={"_csrf_token": token})
        account["email"] = "DUPLICATE@example.com"
        response = self.client.post("/account/register", data=account)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"already registered", response.data)

    def test_direct_checkout_preserves_regular_bag(self):
        token = self.csrf("/product/escobar")
        self.client.post("/cart/add", data={
            "_csrf_token": token, "product_id": "escobar", "qty": "1",
        })
        response = self.client.post("/buy-now", data={
            "_csrf_token": token, "product_id": "gentleman", "qty": "1",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("mode=now", response.headers["Location"])
        page = self.client.get("/checkout?mode=now")
        self.assertIn(b"Gentleman", page.data)
        self.assertNotIn(b"Escobar", page.data)
        response = self.client.post("/checkout", data={
            "_csrf_token": token, "mode": "now", "payment": "Card",
            "customer_name": "Demo direct",
        })
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as s:
            self.assertEqual(s["cart"], {"escobar": 1})
            self.assertNotIn("instant_checkout", s)

    def test_registered_customer_order_history(self):
        token = self.csrf("/account/register")
        self.client.post("/account/register", data={
            "_csrf_token": token, "full_name": "Order Holder",
            "email": "orderholder@example.com", "password": "order-pass-2026",
            "confirm_password": "order-pass-2026",
        })
        self.client.post("/buy-now", data={
            "_csrf_token": token, "product_id": "escobar", "qty": "1",
        })
        purchase = self.client.post("/checkout", data={
            "_csrf_token": token, "mode": "now", "payment": "GCash",
        })
        self.assertEqual(purchase.status_code, 302)
        page = self.client.get("/account")
        self.assertIn(b"Order history", page.data)
        self.assertIn(b"MF-", page.data)
        connection = db.get_db()
        row = connection.execute("SELECT customer_id FROM sales ORDER BY id DESC LIMIT 1").fetchone()
        self.assertIsNotNone(row["customer_id"])
        connection.close()

    def test_invalid_file_upload_is_rejected(self):
        token = self.login()
        response = self.client.post("/admin/products", data={
            "_csrf_token": token, "name": "Safe Scent", "price": 299,
            "cost_price": 120, "stock": 2, "reorder_level": 1,
            "size_label": "50 mL", "description": "Test",
            "image": (io.BytesIO(b"not an image at all"), "dangerous.svg"),
        }, content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Upload a JPG", response.data)
        conn = db.get_db()
        self.assertIsNone(conn.execute("SELECT id FROM products WHERE name='Safe Scent'").fetchone())
        conn.close()


if __name__ == "__main__":
    unittest.main()
