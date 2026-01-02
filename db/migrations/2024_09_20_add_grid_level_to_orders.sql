ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS grid_level INTEGER;

CREATE INDEX IF NOT EXISTS idx_orders_grid_level ON orders(grid_level);
CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_open_grid_level
    ON orders(bot_id, side, grid_level)
    WHERE status IN ('open', 'pending', 'submitting', 'partially_filled')
      AND grid_level IS NOT NULL;
