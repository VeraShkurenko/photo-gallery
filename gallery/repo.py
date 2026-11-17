"""Доступ до MySQL. Усі запити параметризовані (%s), текст користувача
ніколи не вставляється в SQL напряму."""
import pymysql
from pymysql.cursors import DictCursor


class MySQLRepo:
    def __init__(self, host, user, password, database, port=3306):
        self._params = dict(
            host=host, user=user, password=password, database=database,
            port=int(port), charset="utf8mb4", cursorclass=DictCursor,
            autocommit=True, connect_timeout=3, read_timeout=5, write_timeout=5,
        )

    # одне з'єднання на запит Flask (див. gallery/__init__.py)
    def connect(self):
        return pymysql.connect(**self._params)

    def _conn(self):
        from flask import g
        if "db_conn" not in g:
            g.db_conn = self.connect()
        return g.db_conn

    def _all(self, sql, args=()):
        with self._conn().cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall()

    def _one(self, sql, args=()):
        with self._conn().cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchone()

    def _exec(self, sql, args=()):
        with self._conn().cursor() as cur:
            cur.execute(sql, args)
            return cur.lastrowid, cur.rowcount

    # ------------------------------------------------------------ health
    def ping(self):
        row = self._one("SELECT 1 AS ok")
        return row["ok"] == 1

    # ------------------------------------------------------------- users
    def get_user_by_username(self, username):
        return self._one(
            "SELECT id, username, password_hash, role FROM users WHERE username = %s",
            (username,))

    def get_user(self, user_id):
        return self._one("SELECT id, username, role FROM users WHERE id = %s", (user_id,))

    def create_user(self, username, password_hash, role="user"):
        """Повертає id або None, якщо ім'я зайняте (UNIQUE)."""
        try:
            new_id, _ = self._exec(
                "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                (username, password_hash, role))
            return new_id
        except pymysql.err.IntegrityError:
            return None

    # ---------------------------------------------------- login attempts
    def get_login_state(self, username):
        row = self._one(
            "SELECT failed_count, locked_until FROM login_attempts WHERE username = %s",
            (username,))
        return (row["failed_count"], row["locked_until"]) if row else (0, None)

    def set_login_state(self, username, failed_count, locked_until):
        self._exec(
            "INSERT INTO login_attempts (username, failed_count, locked_until) "
            "VALUES (%s, %s, %s) AS new "
            "ON DUPLICATE KEY UPDATE failed_count = new.failed_count, "
            "locked_until = new.locked_until",
            (username, failed_count, locked_until))

    def reset_login_state(self, username):
        self._exec("DELETE FROM login_attempts WHERE username = %s", (username,))

    # -------------------------------------------------------- categories
    def list_categories(self):
        return self._all("SELECT id, name FROM categories ORDER BY id")

    def category_exists(self, category_id):
        return self._one("SELECT id FROM categories WHERE id = %s", (category_id,)) is not None

    # ------------------------------------------------------------- posts
    _POST_SELECT = (
        "SELECT p.id, p.user_id, p.category_id, p.title, p.description, p.s3_key, "
        "p.status, p.created_at, u.username AS author, c.name AS category, "
        "(SELECT COUNT(*) FROM likes l WHERE l.post_id = p.id) AS likes "
        "FROM posts p JOIN users u ON u.id = p.user_id "
        "JOIN categories c ON c.id = p.category_id ")

    def list_approved_posts(self, page, per_page, category_id=None, q=None):
        where = ["p.status = 'approved'"]
        args = []
        if category_id:
            where.append("p.category_id = %s")
            args.append(category_id)
        if q:
            where.append("(p.title LIKE %s OR p.description LIKE %s)")
            pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            args += [pattern, pattern]
        where_sql = "WHERE " + " AND ".join(where)
        total = self._one(
            "SELECT COUNT(*) AS n FROM posts p " + where_sql, tuple(args))["n"]
        posts = self._all(
            self._POST_SELECT + where_sql + " ORDER BY p.created_at DESC, p.id DESC "
            "LIMIT %s OFFSET %s",
            tuple(args) + (per_page, (page - 1) * per_page))
        return posts, total

    def get_post(self, post_id):
        return self._one(self._POST_SELECT + "WHERE p.id = %s", (post_id,))

    def create_post(self, user_id, category_id, title, description, s3_key, status):
        new_id, _ = self._exec(
            "INSERT INTO posts (user_id, category_id, title, description, s3_key, status) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, category_id, title, description, s3_key, status))
        return new_id

    def delete_post(self, post_id):
        self._exec("DELETE FROM posts WHERE id = %s", (post_id,))

    def list_pending_posts(self):
        return self._all(self._POST_SELECT + "WHERE p.status = 'pending' ORDER BY p.created_at")

    def approve_post(self, post_id):
        _, n = self._exec(
            "UPDATE posts SET status = 'approved' WHERE id = %s AND status = 'pending'",
            (post_id,))
        return n > 0

    # ------------------------------------------------ comments and likes
    def list_comments(self, post_id):
        return self._all(
            "SELECT c.id, c.text, c.created_at, u.username AS author "
            "FROM comments c JOIN users u ON u.id = c.user_id "
            "WHERE c.post_id = %s ORDER BY c.created_at, c.id", (post_id,))

    def add_comment(self, post_id, user_id, text):
        self._exec("INSERT INTO comments (post_id, user_id, text) VALUES (%s, %s, %s)",
                   (post_id, user_id, text))

    def add_like(self, post_id, user_id):
        """Повторний лайк ігнорується завдяки UNIQUE(user_id, post_id)."""
        self._exec("INSERT IGNORE INTO likes (post_id, user_id) VALUES (%s, %s)",
                   (post_id, user_id))

    def user_liked(self, post_id, user_id):
        return self._one("SELECT 1 AS x FROM likes WHERE post_id = %s AND user_id = %s",
                         (post_id, user_id)) is not None

    # ------------------------------------------------------------- stats
    def stats(self):
        top_posts = self._all(
            "SELECT p.id, p.title, u.username AS author, COUNT(l.id) AS likes "
            "FROM posts p JOIN users u ON u.id = p.user_id "
            "LEFT JOIN likes l ON l.post_id = p.id "
            "WHERE p.status = 'approved' "
            "GROUP BY p.id, p.title, u.username "
            "ORDER BY likes DESC, p.created_at DESC LIMIT 5")
        per_day = self._all(
            "WITH RECURSIVE days AS ("
            "  SELECT CURDATE() - INTERVAL 6 DAY AS d "
            "  UNION ALL SELECT d + INTERVAL 1 DAY FROM days WHERE d < CURDATE()) "
            "SELECT days.d AS day, COUNT(p.id) AS posts "
            "FROM days LEFT JOIN posts p ON DATE(p.created_at) = days.d "
            "GROUP BY days.d ORDER BY days.d")
        top_authors = self._all(
            "SELECT u.username, COUNT(p.id) AS posts "
            "FROM users u JOIN posts p ON p.user_id = u.id "
            "GROUP BY u.id, u.username ORDER BY posts DESC, u.username LIMIT 3")
        return {"top_posts": top_posts, "per_day": per_day, "top_authors": top_authors}
