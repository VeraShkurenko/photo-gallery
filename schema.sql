-- Фотогалерея — схема бази даних (MySQL 8.0)
-- Застосування (на db, під root через unix-socket):
--   sudo mysql < schema.sql

CREATE DATABASE IF NOT EXISTS gallery
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE gallery;

-- ---------------------------------------------------------------- users
CREATE TABLE IF NOT EXISTS users (
  id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  username      VARCHAR(30)  NOT NULL,
  password_hash VARCHAR(255) NOT NULL,            -- лише хеш (werkzeug scrypt)
  role          ENUM('user', 'admin') NOT NULL DEFAULT 'user',
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_users_username UNIQUE (username)
) ENGINE=InnoDB;

-- ----------------------------------------------------------- categories
CREATE TABLE IF NOT EXISTS categories (
  id   INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(50) NOT NULL,
  CONSTRAINT uq_categories_name UNIQUE (name)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------- posts
CREATE TABLE IF NOT EXISTS posts (
  id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id     INT UNSIGNED NOT NULL,
  category_id INT UNSIGNED NOT NULL,
  title       VARCHAR(100)  NOT NULL,
  description VARCHAR(1000) NOT NULL DEFAULT '',
  s3_key      VARCHAR(255)  NOT NULL,
  status      ENUM('pending', 'approved') NOT NULL DEFAULT 'pending',
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_posts_status_created (status, created_at),
  CONSTRAINT fk_posts_user FOREIGN KEY (user_id)
    REFERENCES users (id) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_posts_category FOREIGN KEY (category_id)
    REFERENCES categories (id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- ------------------------------------------------------------- comments
CREATE TABLE IF NOT EXISTS comments (
  id         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  post_id    INT UNSIGNED NOT NULL,
  user_id    INT UNSIGNED NOT NULL,
  text       VARCHAR(1000) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_comments_post FOREIGN KEY (post_id)
    REFERENCES posts (id) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_comments_user FOREIGN KEY (user_id)
    REFERENCES users (id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------- likes
CREATE TABLE IF NOT EXISTS likes (
  id      INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  post_id INT UNSIGNED NOT NULL,
  user_id INT UNSIGNED NOT NULL,
  CONSTRAINT uq_likes_user_post UNIQUE (user_id, post_id),
  CONSTRAINT fk_likes_post FOREIGN KEY (post_id)
    REFERENCES posts (id) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_likes_user FOREIGN KEY (user_id)
    REFERENCES users (id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

-- ----------------------------------------------------------- action_log
-- Заповнюється лише тригерами (див. нижче), код застосунку сюди не пише.
CREATE TABLE IF NOT EXISTS action_log (
  id         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id    INT UNSIGNED NULL,
  action     VARCHAR(100) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_action_log_user FOREIGN KEY (user_id)
    REFERENCES users (id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB;

-- ------------------------------------------------------- login_attempts
-- Допоміжна таблиця для ліміту 5 невдалих спроб входу (спільна для обох web).
CREATE TABLE IF NOT EXISTS login_attempts (
  username     VARCHAR(255) NOT NULL PRIMARY KEY,
  failed_count INT UNSIGNED NOT NULL DEFAULT 0,
  locked_until DATETIME NULL
) ENGINE=InnoDB;

-- ------------------------------------------------- початкові категорії
INSERT IGNORE INTO categories (name) VALUES
  ('Природа'), ('Місто'), ('Люди'), ('Тварини'), ('Інше');

-- -------------------------------------------------------------- тригери
DROP TRIGGER IF EXISTS trg_posts_after_insert;
DROP TRIGGER IF EXISTS trg_posts_after_delete;
DROP TRIGGER IF EXISTS trg_posts_after_update;

DELIMITER //

CREATE TRIGGER trg_posts_after_insert
AFTER INSERT ON posts FOR EACH ROW
BEGIN
  INSERT INTO action_log (user_id, action)
  VALUES (NEW.user_id, CONCAT('post_created #', NEW.id));
END//

CREATE TRIGGER trg_posts_after_delete
AFTER DELETE ON posts FOR EACH ROW
BEGIN
  INSERT INTO action_log (user_id, action)
  VALUES (OLD.user_id, CONCAT('post_deleted #', OLD.id));
END//

CREATE TRIGGER trg_posts_after_update
AFTER UPDATE ON posts FOR EACH ROW
BEGIN
  IF OLD.status = 'pending' AND NEW.status = 'approved' THEN
    INSERT INTO action_log (user_id, action)
    VALUES (NEW.user_id, CONCAT('post_approved #', NEW.id));
  END IF;
END//

DELIMITER ;
