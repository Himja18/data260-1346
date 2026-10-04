-- HW5 Part 1: extend s1346_rel for the related entity (transit_lines) and
-- the primary entity (incidents). Run ONCE against the existing HW4 database:
--   mysql -u root -p < code/backend/migrations/003_hw5_related_entity.sql
-- Safe on the seeded data: incident_code is backfilled from the id before it
-- becomes NOT NULL + UNIQUE.
USE s1346_rel;

-- 1. transit_lines: add timestamps -----------------------------------------
ALTER TABLE transit_lines
  ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                  ON UPDATE CURRENT_TIMESTAMP;

-- 2. incidents: unique code, numeric field with default, updated_at --------
ALTER TABLE incidents
  ADD COLUMN incident_code VARCHAR(10) NULL AFTER id,
  ADD COLUMN passengers_affected INT NOT NULL DEFAULT 0 AFTER category,
  ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                  ON UPDATE CURRENT_TIMESTAMP;

UPDATE incidents SET incident_code = CONCAT('INC-', LPAD(id, 6, '0'))
 WHERE incident_code IS NULL;

ALTER TABLE incidents
  MODIFY incident_code VARCHAR(10) NOT NULL,
  ADD CONSTRAINT uq_incident_code UNIQUE (incident_code),
  ADD CONSTRAINT ck_passengers_nonneg CHECK (passengers_affected >= 0);

-- 3. FK: block deleting a line that still has incidents ---------------------
-- HW4 used ON DELETE SET NULL, which silently orphaned incidents.
ALTER TABLE incidents DROP FOREIGN KEY fk_incident_line;
ALTER TABLE incidents
  ADD CONSTRAINT fk_incident_line FOREIGN KEY (line_id)
      REFERENCES transit_lines(id) ON DELETE RESTRICT ON UPDATE CASCADE;
