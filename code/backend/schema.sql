-- DATA-260 HW5 schema for s1346_rel (fresh install).
-- Existing HW4 databases: run migrations/003_hw5_related_entity.sql instead.
-- Run:  mysql -u root -p < code/backend/schema.sql

CREATE DATABASE IF NOT EXISTS s1346_rel
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE s1346_rel;

CREATE TABLE IF NOT EXISTS transit_lines (
  id    INT AUTO_INCREMENT PRIMARY KEY,
  code  VARCHAR(20)  NOT NULL UNIQUE,
  name  VARCHAR(100) NOT NULL,
  mode  VARCHAR(20)  NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS incidents (
  id                  INT AUTO_INCREMENT PRIMARY KEY,
  incident_code       VARCHAR(10)  NOT NULL UNIQUE,     -- unique field, INC-000123
  route_title         VARCHAR(200) NOT NULL,            -- primary field
  category            VARCHAR(50)  NOT NULL,            -- secondary field
  passengers_affected INT          NOT NULL DEFAULT 0,  -- numeric field w/ default
  line_id             INT NULL,
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT ck_passengers_nonneg CHECK (passengers_affected >= 0),
  CONSTRAINT fk_incident_line FOREIGN KEY (line_id) REFERENCES transit_lines(id)
    ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS users (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  name          VARCHAR(100) NOT NULL,
  email         VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sessions (
  id         VARCHAR(64) PRIMARY KEY,          -- opaque session token
  user_id    INT      NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at DATETIME NOT NULL,
  CONSTRAINT fk_session_user FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE
) ENGINE=InnoDB;
