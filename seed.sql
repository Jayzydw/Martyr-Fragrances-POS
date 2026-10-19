-- Starting rows. This file runs only when the users table is empty.
-- The initial demo password is migrated to a salted password hash by db.py.
-- No plaintext passwords are stored in the database.

INSERT INTO users (username, password_hash, full_name) VALUES (
    'admin',
    'ad872b4820b164b7a25695ff77d0f6e5df812c6f9944d1d21461f57f099bce57',
    'House admin'
);

INSERT INTO products (
    id, name, price, cost_price, stock, reorder_level, size_label, image,
    blurb, description, season, longevity, rating
) VALUES
('escobar', 'Escobar', 299, 120, 16, 5, '50 mL', '/brand/refined/25-14fc31e8.webp',
 'A dark, resinous opening with a clean citrus edge.',
 'Escobar is the house''s evening signature. Bitter orange and spice open the top, then a dry leather-and-wood base stays close to the skin.',
 'Night / Autumn', '6–8 hours', 5),
('el-patron', 'El Patron', 299, 118, 4, 5, '50 mL', '/brand/refined/27-3094994e.webp',
 'Bold, magnetic, and the classic sailor.',
 'El Patron balances tradition and sensuality. Fresh mint and lavender recall a barbershop, while warm vanilla and cinnamon create a deep, masculine allure.',
 'Day / All year', '6–8 hours', 5),
('gentleman', 'Gentleman', 299, 115, 11, 5, '50 mL', '/brand/refined/31-b1fa48ff.webp',
 'Timeless, versatile, and professional.',
 'The ultimate blue fragrance. It opens with a sharp, clean burst of citrus and peppermint, then a woody heart of cedar and sandalwood.',
 'Day / Spring', '6–8 hours', 5),
('midnight-blaze', 'Midnight Blaze', 299, 122, 0, 5, '50 mL', '/brand/refined/26-c10878dc.webp',
 'Warm, spicy, and quietly magnetic.',
 'A modern magnetic scent centered on cardamom, pink pepper, and violet leaf, with vanilla and crystallized chestnut.',
 'Night / Winter', '6–8 hours', 4),
('equinox', 'Equinox', 399, 170, 8, 4, '50 mL', NULL,
 'The balance between daylight and after-dark.',
 'Equinox is the house''s limited balance. Bright bergamot at noon, a soft incense trail by evening.',
 'Day to night', '7–9 hours', 5),
('unreleased-2', 'Unreleased 2', 399, 180, 6, 4, '50 mL', NULL,
 'A limited red-label study in rose and smoke.',
 'Unreleased 2 is a small-batch study. Rose sits over a smoked wood base, finished with a dry pepper snap.',
 'Evening', '7–9 hours', 4),
('unreleased-1', 'Unreleased 1', 399, 185, 3, 4, '50 mL', '/brand/refined/24-bf49f503.webp',
 'This smells like success — but not in a loud way.',
 'Opens with a fresh, slightly sharp pineapple that quickly turns smoky and woody.',
 'Evening / All year', '7–9 hours', 5);

INSERT INTO product_accords (product_id, name, level) VALUES
('escobar', 'citrus', 6),
('escobar', 'spicy', 7),
('escobar', 'leather', 5),
('escobar', 'woody', 8),
('escobar', 'amber', 4),
('el-patron', 'aromatic', 7),
('el-patron', 'vanilla', 6),
('el-patron', 'lavender', 6),
('el-patron', 'woody', 5),
('gentleman', 'citrus', 8),
('gentleman', 'fresh', 7),
('gentleman', 'woody', 6),
('gentleman', 'aromatic', 5),
('midnight-blaze', 'warm spicy', 8),
('midnight-blaze', 'vanilla', 7),
('midnight-blaze', 'soft spicy', 6),
('midnight-blaze', 'sweet', 5),
('equinox', 'bergamot', 7),
('equinox', 'woods', 6),
('equinox', 'incense', 5),
('equinox', 'musk', 4),
('unreleased-2', 'rose', 7),
('unreleased-2', 'smoke', 6),
('unreleased-2', 'pepper', 5),
('unreleased-2', 'woody', 5),
('unreleased-1', 'woody', 8),
('unreleased-1', 'pineapple', 7),
('unreleased-1', 'smoky', 6),
('unreleased-1', 'fresh', 4);

INSERT INTO sales (
    sale_number, sold_at, channel, payment_method, customer_name,
    subtotal, total, tendered, change_amount
) VALUES (
    'MF-2401', '2026-03-02 14:10', 'in-store', 'Cash', 'Walk-in',
    598, 598, 600, 2
);

INSERT INTO sale_items (sale_id, product_id, product_name, quantity, unit_price, unit_cost, line_total)
VALUES (1, 'escobar', 'Escobar', 2, 299, 120, 598);

INSERT INTO inventory_history (product_id, product_name, change_qty, reason, note, created_at)
VALUES ('escobar', 'Escobar', -2, 'sale', 'MF-2401', '2026-03-02 14:10');

INSERT INTO expenses (spent_on, category, amount, note) VALUES
('2026-03-01', 'Bottles', 2400, 'Glass for the next batch'),
('2026-03-04', 'Labels', 860, 'Gold foil labels');

INSERT INTO reviews (author_name, product_name, stars, quote) VALUES
('Andre L.', 'Gentleman', 5, 'Clean enough for a morning meeting and still there when I leave the office.'),
('Marco V.', 'El Patron', 5, 'Barbershop lavender without smelling like a costume. The vanilla stays polite.'),
('Jia R.', 'Unreleased 1', 5, 'Pineapple that does not shout, then smoke. Someone asked what it was both times.'),
('Paolo S.', 'Midnight Blaze', 4, 'Warm cardamom, not a sweet candy spice. Better after dark than at noon.'),
('Elena C.', 'Escobar', 5, 'Dry wood and a little bitterness. It feels expensive without the heavy projection.'),
('Renzo D.', 'Equinox', 4, 'The one I take when I do not know if the night will stay a day.');
