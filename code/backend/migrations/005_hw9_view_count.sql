-- HW9 Part 1: persisted view counter for the primary entity (incidents).
-- Redis holds the live count (s1346:views:incident:<id>); every 10 views it is written here.
-- Run ONCE on the HW7/HW8 database:
--   mysql -u root -p < code/backend/migrations/005_hw9_view_count.sql
USE s1346_rel;

ALTER TABLE incidents
  ADD COLUMN view_count INT NOT NULL DEFAULT 0 AFTER passengers_affected,
  ADD CONSTRAINT ck_view_count_nonneg CHECK (view_count >= 0);
