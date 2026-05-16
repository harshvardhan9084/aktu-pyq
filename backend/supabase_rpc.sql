-- Run this in Supabase SQL Editor alongside schema.sql
-- Provides atomic counter increment used by analytics

CREATE OR REPLACE FUNCTION increment_counter(counter_key TEXT, delta BIGINT DEFAULT 1)
RETURNS VOID AS $$
BEGIN
  INSERT INTO site_counters (key, value, updated_at)
  VALUES (counter_key, delta, NOW())
  ON CONFLICT (key)
  DO UPDATE SET
    value = site_counters.value + delta,
    updated_at = NOW();
END;
$$ LANGUAGE plpgsql;
