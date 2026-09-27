-- DATA-260 HW4 schema for s1346_rel
-- Run:  mysql -u root -p < code/backend/schema.sql

CREATE DATABASE IF NOT EXISTS s1346_rel
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE s1346_rel;

CREATE TABLE IF NOT EXISTS transit_lines (
  id    INT AUTO_INCREMENT PRIMARY KEY,
  code  VARCHAR(20)  NOT NULL UNIQUE,
  name  VARCHAR(100) NOT NULL,
  mode  VARCHAR(20)  NOT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS incidents (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  route_title VARCHAR(200) NOT NULL,          -- primary field
  category    VARCHAR(50)  NOT NULL,          -- secondary field
  line_id     INT NULL,
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_incident_line FOREIGN KEY (line_id) REFERENCES transit_lines(id)
    ON DELETE SET NULL
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
