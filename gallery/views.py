"""Маршрути застосунку (розділ 5.3 ТЗ)."""
import math
import uuid

from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect,
                   render_template, request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from . import security, validation as v

bp = Blueprint("main", __name__)


def repo():
    return current_app.repo


def storage():
    return current_app.storage


def _int_arg(name, default=None):
    try:
        return int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default


def _safe_next(target):
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("main.index")


# ------------------------------------------------------------------ main
@bp.get("/")
def index():
    page = max(_int_arg("page", 1) or 1, 1)
    category_id = _int_arg("category")
    q = (request.args.get("q") or "").strip()[:100]
    per_page = current_app.config["POSTS_PER_PAGE"]
    posts, total = repo().list_approved_posts(page, per_page, category_id, q or None)
    pages = max(math.ceil(total / per_page), 1)
    return render_template("index.html", posts=posts, page=page, pages=pages, total=total,
                           categories=repo().list_categories(),
                           category_id=category_id, q=q)


# ------------------------------------------------------------------ auth
@bp.route("/register", methods=["GET", "POST"])
def register():
    error = None
    username = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        error = v.validate_username(username) or v.validate_password(password)
        if not error:
            if repo().get_user_by_username(username) is not None:
                error = v.ERR_USERNAME_TAKEN
            else:
                new_id = repo().create_user(username, generate_password_hash(password))
                if new_id is None:
                    error = v.ERR_USERNAME_TAKEN
                else:
                    security.login_user({"id": new_id})
                    flash("Реєстрація успішна. Ласкаво просимо!", "success")
                    return redirect(url_for("main.index"))
    return render_template("register.html", error=error, username=username), (400 if error else 200)


@bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    username = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()[:255]
        password = request.form.get("password") or ""
        if security.is_locked(repo(), username):
            error = v.ERR_TOO_MANY
        else:
            user = repo().get_user_by_username(username) if username else None
            if user and check_password_hash(user["password_hash"], password):
                repo().reset_login_state(username)
                security.login_user(user)
                return redirect(_safe_next(request.args.get("next")))
            security.register_failure(repo(), username)
            error = v.ERR_BAD_LOGIN
    return render_template("login.html", error=error, username=username), (401 if error else 200)


@bp.post("/logout")
@security.login_required
def logout():
    session.clear()
    flash("Ви вийшли з облікового запису.", "success")
    return redirect(url_for("main.index"))


# ----------------------------------------------------------------- posts
@bp.route("/post/new", methods=["GET", "POST"])
@security.login_required
def post_new():
    categories = repo().list_categories()
    form = {"title": "", "description": "", "category_id": ""}
    error = None
    if request.method == "POST":
        form = {k: (request.form.get(k) or "") for k in form}
        title = form["title"].strip()
        description = form["description"].strip()
        image = request.files.get("image")
        try:
            category_id = int(form["category_id"])
        except ValueError:
            category_id = None
        error = v.validate_title(title) or v.validate_description(description)
        if not error and (category_id is None or not repo().category_exists(category_id)):
            error = v.ERR_CATEGORY
        mime = ext = None
        if not error:
            data = image.read() if image else b""
            error, mime, ext = v.validate_image(image.filename if image else "", data)
        if not error:
            key = f"images/{uuid.uuid4().hex}.{ext}"
            storage().upload(key, data, mime)
            status = "approved" if g.user["role"] == "admin" else "pending"
            try:
                post_id = repo().create_post(g.user["id"], category_id, title, description, key, status)
            except Exception:
                storage().delete(key)
                raise
            if status == "pending":
                flash("Пост надіслано на модерацію. Він з'явиться після схвалення адміністратором.", "info")
            else:
                flash("Пост опубліковано.", "success")
            return redirect(url_for("main.post_view", post_id=post_id))
    return render_template("post_new.html", categories=categories, form=form,
                           error=error), (400 if error else 200)


@bp.app_errorhandler(413)
def too_large(e):
    if request.path == url_for("main.post_new") and g.get("user"):
        return render_template("post_new.html", categories=repo().list_categories(),
                               form={"title": "", "description": "", "category_id": ""},
                               error=v.ERR_IMAGE), 413
    return render_template("error.html", code=413, message=v.ERR_IMAGE), 413


def _visible_post(post_id):
    post = repo().get_post(post_id)
    if post is None:
        abort(404)
    if post["status"] != "approved":
        user = g.get("user")
        if not user or (user["role"] != "admin" and user["id"] != post["user_id"]):
            abort(404)
    return post


@bp.get("/post/<int:post_id>")
def post_view(post_id):
    post = _visible_post(post_id)
    liked = bool(g.user) and repo().user_liked(post_id, g.user["id"])
    return render_template("post.html", post=post, comments=repo().list_comments(post_id),
                           liked=liked, comment_error=None)


@bp.post("/post/<int:post_id>/delete")
@security.login_required
def post_delete(post_id):
    post = repo().get_post(post_id)
    if post is None:
        abort(404)
    if g.user["role"] != "admin" and g.user["id"] != post["user_id"]:
        return render_template("error.html", code=403,
                               message="Ви не можете видалити чужий пост. Пост не змінено."), 403
    repo().delete_post(post_id)
    storage().delete(post["s3_key"])
    flash("Пост видалено.", "success")
    return redirect(url_for("main.index"))


@bp.post("/post/<int:post_id>/comment")
@security.login_required
def post_comment(post_id):
    post = _visible_post(post_id)
    text = (request.form.get("text") or "").strip()
    error = v.validate_comment(text)
    if error:
        return render_template("post.html", post=post, comments=repo().list_comments(post_id),
                               liked=repo().user_liked(post_id, g.user["id"]),
                               comment_error=error), 400
    repo().add_comment(post_id, g.user["id"], text)
    return redirect(url_for("main.post_view", post_id=post_id) + "#comments")


@bp.post("/post/<int:post_id>/like")
@security.login_required
def post_like(post_id):
    _visible_post(post_id)
    repo().add_like(post_id, g.user["id"])
    return redirect(url_for("main.post_view", post_id=post_id))


# ----------------------------------------------------------------- admin
@bp.get("/admin/moderation")
@security.admin_required
def moderation():
    return render_template("moderation.html", posts=repo().list_pending_posts())


@bp.post("/admin/post/<int:post_id>/approve")
@security.admin_required
def approve(post_id):
    if repo().get_post(post_id) is None:
        abort(404)
    repo().approve_post(post_id)
    flash("Пост схвалено й опубліковано.", "success")
    return redirect(url_for("main.moderation"))


# ----------------------------------------------------------- stats/health
@bp.get("/stats")
def stats():
    return render_template("stats.html", stats=repo().stats())


@bp.get("/health")
def health():
    result = {"status": "ok", "db": "ok", "s3": "ok", "host": current_app.hostname}
    try:
        if not repo().ping():
            raise RuntimeError("db ping failed")
    except Exception as exc:  # noqa: BLE001
        current_app.logger.warning("health: db fail: %s", exc)
        result["db"] = "fail"
    try:
        storage().check()
    except Exception as exc:  # noqa: BLE001
        current_app.logger.warning("health: s3 fail: %s", exc)
        result["s3"] = "fail"
    if result["db"] != "ok" or result["s3"] != "ok":
        result["status"] = "fail"
        return jsonify(result), 503
    return jsonify(result), 200
