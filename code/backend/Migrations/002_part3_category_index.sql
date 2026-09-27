-- HW4 Part 3.8: the one added index.
-- Speeds up "incidents of one category, newest first" (the /api/incidents/fixed?category=...
-- query). InnoDB secondary indexes also store the primary key, so (category) + id order
-- lets MySQL read matching rows straight from the index instead of scanning the table.
-- (line_id already has an index: MySQL creates one automatically for the FK.)
USE s1346_rel;
CREATE INDEX ix_incidents_category ON incidents (category);
