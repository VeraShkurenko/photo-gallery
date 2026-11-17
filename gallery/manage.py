"""Службові команди: python -m gallery.manage create-admin <username>
Пароль читається з stdin (не з аргументів, щоб не потрапив у history)."""
import getpass
import os
import sys

from werkzeug.security import generate_password_hash

from .repo import MySQLRepo
from .validation import validate_password, validate_username


def main():
    if len(sys.argv) != 3 or sys.argv[1] != "create-admin":
        print(__doc__)
        sys.exit(2)
    username = sys.argv[2]
    password = getpass.getpass("Пароль адміністратора: ") if sys.stdin.isatty() else sys.stdin.readline().rstrip("\n")
    err = validate_username(username) or validate_password(password)
    if err:
        sys.exit(err)
    repo = MySQLRepo(os.environ["DB_HOST"], os.environ["DB_USER"],
                     os.environ["DB_PASSWORD"], os.environ.get("DB_NAME", "gallery"))
    conn = repo.connect()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'admin') "
            "AS new ON DUPLICATE KEY UPDATE password_hash = new.password_hash, role = 'admin'",
            (username, generate_password_hash(password)))
    conn.close()
    print(f"Адміністратор {username} готовий.")


if __name__ == "__main__":
    main()
