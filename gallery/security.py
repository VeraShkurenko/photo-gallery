"""CSRF, сесії з тайм-аутом бездіяльності, ліміт спроб входу, декоратори доступу."""
import secrets
import time
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import abort, current_app, g, redirect, request, session, url_for

SESSION_IDLE_SECONDS = 30 * 60
MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ------------------------------------------------------------------ CSRF
def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def check_csrf():
    if request.method != "POST":
        return
    sent = request.form.get("csrf_token", "")
    expected = session.get("csrf", "")
    if not expected or not secrets.compare_digest(sent, expected):
        abort(400, description="Недійсний CSRF-токен. Оновіть сторінку й спробуйте ще раз.")


# -------------------------------------------------------- session idle
def load_user():
    """Викликається перед кожним запитом: завершує сесію після 30 хв бездіяльності
    і завантажує поточного користувача."""
    g.user = None
    now = int(time.time())
    last = session.get("last_seen")
    if "user_id" in session and last is not None and now - last > SESSION_IDLE_SECONDS:
        session.clear()
    if "user_id" in session:
        session["last_seen"] = now
        g.user = current_app.repo.get_user(session["user_id"])
        if g.user is None:
            session.clear()


def login_user(user):
    csrf = session.get("csrf")
    session.clear()
    session.permanent = True
    session["user_id"] = user["id"]
    session["last_seen"] = int(time.time())
    if csrf:
        session["csrf"] = csrf


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            return redirect(url_for("main.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            return redirect(url_for("main.login", next=request.path))
        if g.user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


# --------------------------------------------------------- login limit
def is_locked(repo, username):
    _, locked_until = repo.get_login_state(username)
    return locked_until is not None and locked_until > utcnow()


def register_failure(repo, username):
    failed, locked_until = repo.get_login_state(username)
    if locked_until is not None and locked_until <= utcnow():
        failed = 0  # блокування минуло — рахуємо заново
    failed += 1
    new_lock = utcnow() + timedelta(minutes=LOCK_MINUTES) if failed >= MAX_FAILED_LOGINS else None
    repo.set_login_state(username, failed, new_lock)
