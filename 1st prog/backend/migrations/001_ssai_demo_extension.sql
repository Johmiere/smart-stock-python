-- Apply after database/groupmate_clean_setup.sql, to inventory_group_demo only.
-- This adds the fields needed for the SSAI demo while retaining current tables.

ALTER TABLE product
  ADD COLUMN IF NOT EXISTS product_category VARCHAR(40) NOT NULL DEFAULT 'Other',
  ADD COLUMN IF NOT EXISTS product_unit VARCHAR(30) NOT NULL DEFAULT 'pieces',
  ADD COLUMN IF NOT EXISTS product_price DECIMAL(10,2) NOT NULL DEFAULT 0.00,
  ADD COLUMN IF NOT EXISTS reorder_level INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS supplier_lead_time_days INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS safety_stock_units INT NOT NULL DEFAULT 0;

ALTER TABLE credential
  ADD UNIQUE INDEX IF NOT EXISTS uq_credential_username (cre_username);

CREATE TABLE IF NOT EXISTS sale_transaction (
  transaction_id BIGINT NOT NULL AUTO_INCREMENT,
  store_id BIGINT NOT NULL,
  users_id BIGINT NOT NULL,
  subtotal DECIMAL(12,2) NOT NULL DEFAULT 0.00,
  discount_type ENUM('none','pwd','senior') NOT NULL DEFAULT 'none',
  discount_reference VARCHAR(40) DEFAULT NULL,
  discount_amount DECIMAL(12,2) NOT NULL DEFAULT 0.00,
  total_amount DECIMAL(12,2) NOT NULL DEFAULT 0.00,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (transaction_id),
  KEY idx_sale_transaction_store_date (store_id, created_at),
  CONSTRAINT fk_sale_transaction_store FOREIGN KEY (store_id) REFERENCES store (store_id),
  CONSTRAINT fk_sale_transaction_user FOREIGN KEY (users_id) REFERENCES users (users_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

ALTER TABLE sales
  ADD COLUMN IF NOT EXISTS sale_transaction_id BIGINT NULL,
  ADD COLUMN IF NOT EXISTS sale_unit_price DECIMAL(10,2) NOT NULL DEFAULT 0.00,
  ADD COLUMN IF NOT EXISTS sale_discount_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00,
  ADD INDEX IF NOT EXISTS idx_sales_transaction (sale_transaction_id);

CREATE TABLE IF NOT EXISTS stock_batch (
  batch_id BIGINT NOT NULL AUTO_INCREMENT,
  product_id BIGINT NOT NULL,
  store_id BIGINT NOT NULL,
  quantity_received INT NOT NULL,
  quantity_remaining INT NOT NULL,
  received_at DATETIME DEFAULT NULL,
  expiry_date DATE DEFAULT NULL,
  notes VARCHAR(255) DEFAULT NULL,
  source_key VARCHAR(64) DEFAULT NULL,
  created_by BIGINT DEFAULT NULL,
  PRIMARY KEY (batch_id),
  UNIQUE KEY uq_stock_batch_source (source_key),
  KEY idx_batch_product_expiry (product_id, expiry_date, quantity_remaining),
  KEY idx_batch_store_expiry (store_id, expiry_date),
  CONSTRAINT fk_stock_batch_product FOREIGN KEY (product_id) REFERENCES product (product_id),
  CONSTRAINT fk_stock_batch_store FOREIGN KEY (store_id) REFERENCES store (store_id),
  CONSTRAINT fk_stock_batch_user FOREIGN KEY (created_by) REFERENCES users (users_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

ALTER TABLE stock_movement
  ADD COLUMN IF NOT EXISTS batch_id BIGINT NULL,
  ADD COLUMN IF NOT EXISTS sales_id BIGINT NULL,
  ADD INDEX IF NOT EXISTS idx_movement_batch (batch_id),
  ADD INDEX IF NOT EXISTS idx_movement_sales (sales_id);

-- Existing aggregate quantities do not reveal their expiry dates. Keep them
-- as legacy batches with NULL expiry instead of inventing expiry information.
INSERT INTO stock_batch
  (product_id, store_id, quantity_received, quantity_remaining, received_at, expiry_date, notes, source_key)
SELECT p.product_id, p.store_id, COALESCE(p.product_quantity, 0), COALESCE(p.product_quantity, 0),
       NULL, NULL, 'Legacy aggregate stock; expiry and receipt date unknown',
       CONCAT('legacy-product-', p.product_id)
FROM product p
WHERE COALESCE(p.product_quantity, 0) > 0
ON DUPLICATE KEY UPDATE source_key = VALUES(source_key);

