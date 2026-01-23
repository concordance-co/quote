-- Reset sqlx migration tracking
-- This allows the server to re-apply migrations from scratch

DROP TABLE IF EXISTS _sqlx_migrations;
