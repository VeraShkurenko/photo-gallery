"""Фотогалерея — Flask-застосунок.

Конфігурація лише зі змінних оточення (на сервері — /etc/gallery.env, права 600,
поза репозиторієм):
  SECRET_KEY, DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, S3_BUCKET, AWS_REGION,
  STUDENT_NAME
"""
import os
import socket
from datetime import timedelta

from flask import Flask, g, render_template

from . import security


def create_app(repo=None, storage=None, config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        STUDENT_NAME=os.environ.get("STUDENT_NAME", "Shkurenko"),
        PERMANENT_SESSION_LIFETIME=timedelta(seconds=security.SESSION_IDLE_SECONDS),
        SESSION_REFRESH_EACH_REQUEST=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # трохи більше за 5 МБ, щоб файл 5–10 МБ дійшов до валідації і
        # отримав зрозуміле повідомлення; більші файли — обробник 413
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
        POSTS_PER_PAGE=6,
    )
    if config:
        app.config.update(config)
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("SECRET_KEY не задано (див. /etc/gallery.env)")

    if repo is None:
        from .repo import MySQLRepo
        repo = MySQLRepo(
            host=os.environ["DB_HOST"], user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"], database=os.environ.get("DB_NAME", "gallery"))
    if storage is None:
        from .storage import S3Storage
        storage = S3Storage(os.environ["S3_BUCKET"], os.environ.get("AWS_REGION", "us-east-1"))
    app.json.sort_keys = False  # порядок полів як у ТЗ: status, db, s3, host
    app.repo = repo
    app.storage = storage
    app.hostname = socket.gethostname()

    @app.before_request
    def _before():
        security.check_csrf()
        security.load_user()

    @app.teardown_appcontext
    def _close_db(exc):
        conn = g.pop("db_conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    @app.context_processor
    def _inject():
        return {
            "csrf_token": security.csrf_token,
            "current_user": g.get("user"),
            "student_name": app.config["STUDENT_NAME"],
            "hostname": app.hostname,
            "image_url": app.storage.url,
        }

    from .views import bp
    app.register_blueprint(bp)

    @app.errorhandler(400)
    def _400(e):
        return render_template("error.html", code=400, message=e.description), 400

    @app.errorhandler(403)
    def _403(e):
        return render_template("error.html", code=403,
                               message="Доступ заборонено: у вас немає прав на цю дію."), 403

    @app.errorhandler(404)
    def _404(e):
        return render_template("error.html", code=404, message="Сторінку не знайдено."), 404

    @app.errorhandler(405)
    def _405(e):
        return render_template("error.html", code=405,
                               message="Метод не дозволено (дії, що змінюють дані, — лише POST)."), 405

    return app
