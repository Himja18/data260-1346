-- HW7 Part 1: users table for JWT login with roles. Run ONCE on the HW6 database:
--   mysql -u root -p < code/backend/migrations/004_hw7_jwt_roles.sql
-- The HW4/HW5 server-side `sessions` table is no longer used by any HW7 route; it is
-- dropped here (the cookie-session implementation lives on only at the hw4 tag).
USE s1346_rel;

ALTER TABLE users
  ADD COLUMN username VARCHAR(50) NULL AFTER id,
  ADD COLUMN role ENUM('reader', 'writer', 'moderator') NOT NULL DEFAULT 'reader'
             AFTER password_hash,
  MODIFY name  VARCHAR(100) NULL,
  MODIFY email VARCHAR(255) NULL;

-- Existing HW4/HW5 account(s): username = part of the email before '@'.
-- The original dispatcher keeps full rights as a moderator.
UPDATE users SET username = LOWER(SUBSTRING_INDEX(email, '@', 1)) WHERE username IS NULL;
UPDATE users SET role = 'moderator' WHERE username = 'dispatcher1346';

ALTER TABLE users
  MODIFY username VARCHAR(50) NOT NULL,
  ADD CONSTRAINT uq_users_username UNIQUE (username);

DROP TABLE IF EXISTS sessions;
