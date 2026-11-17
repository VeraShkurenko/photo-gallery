"""Тести без справжніх MySQL/S3: застосунок отримує in-memory підробки."""
import re
from datetime import datetime

import pytest
from werkzeug.security import generate_password_hash

from gallery import create_app


class FakeRepo:
    def __init__(self):
        self.users, self.posts, self.likes, self.comments, self.attempts = {}, {}, set(), [], {}
        self.categories = [{"id": i, "name": n} for i, n in
                           enumerate(["Природа", "Місто", "Люди", "Тварини", "Інше"], 1)]
        self.db_ok = True

    def ping(self):
        if not self.db_ok:
            raise ConnectionError("db down")
        return True

    def get_user_by_username(self, username):
        return next((u for u in self.users.values() if u["username"] == username), None)

    def get_user(self, uid):
        return self.users.get(uid)

    def create_user(self, username, password_hash, role="user"):
        if self.get_user_by_username(username):
            return None
        uid = len(self.users) + 1
        self.users[uid] = {"id": uid, "username": username, "password_hash": password_hash, "role": role}
        return uid

    def get_login_state(self, username):
        return self.attempts.get(username, (0, None))

    def set_login_state(self, username, failed, locked_until):
        self.attempts[username] = (failed, locked_until)

    def reset_login_state(self, username):
        self.attempts.pop(username, None)

    def list_categories(self):
        return self.categories

    def category_exists(self, cid):
        return any(c["id"] == cid for c in self.categories)

    def _full(self, p):
        return dict(p, author=self.users[p["user_id"]]["username"],
                    category=self.categories[p["category_id"] - 1]["name"],
                    likes=sum(1 for (pid, _) in self.likes if pid == p["id"]))

    def list_approved_posts(self, page, per_page, category_id=None, q=None):
        items = [self._full(p) for p in self.posts.values() if p["status"] == "approved"
                 and (not category_id or p["category_id"] == category_id)
                 and (not q or q in p["title"] or q in p["description"])]
        items.sort(key=lambda p: p["id"], reverse=True)
        return items[(page - 1) * per_page: page * per_page], len(items)

    def get_post(self, pid):
        p = self.posts.get(pid)
        return self._full(p) if p else None

    def create_post(self, user_id, category_id, title, description, s3_key, status):
        pid = len(self.posts) + 100
        self.posts[pid] = dict(id=pid, user_id=user_id, category_id=category_id, title=title,
                               description=description, s3_key=s3_key, status=status,
                               created_at=datetime(2026, 11, 18, 12, 0))
        return pid

    def delete_post(self, pid):
        self.posts.pop(pid, None)

    def list_pending_posts(self):
        return [self._full(p) for p in self.posts.values() if p["status"] == "pending"]

    def approve_post(self, pid):
        self.posts[pid]["status"] = "approved"
        return True

    def list_comments(self, pid):
        return [c for c in self.comments if c["post_id"] == pid]

    def add_comment(self, pid, uid, text):
        self.comments.append({"post_id": pid, "author": self.users[uid]["username"], "text": text,
                              "created_at": datetime(2026, 11, 18, 12, 0)})

    def add_like(self, pid, uid):
        self.likes.add((pid, uid))

    def user_liked(self, pid, uid):
        return (pid, uid) in self.likes

    def stats(self):
        return {"top_posts": [], "per_day": [], "top_authors": []}


class FakeStorage:
    def __init__(self):
        self.objects, self.ok = {}, True

    def check(self):
        if not self.ok:
            raise ConnectionError("s3 down")
        return True

    def upload(self, key, data, content_type):
        self.objects[key] = data

    def delete(self, key):
        self.objects.pop(key, None)

    def url(self, key, expires=3600):
        return f"https://gallery-test.s3.amazonaws.com/{key}?X-Amz-Signature=x"


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 100


@pytest.fixture
def repo():
    r = FakeRepo()
    r.create_user("admin", generate_password_hash("adminpass123"), "admin")
    r.create_user("alice", generate_password_hash("alicepass123"))
    r.create_user("bob", generate_password_hash("bobpass1234"))
    return r


@pytest.fixture
def storage():
    return FakeStorage()


@pytest.fixture
def app(repo, storage):
    return create_app(repo=repo, storage=storage,
                      config={"SECRET_KEY": "test", "TESTING": True, "STUDENT_NAME": "Shkurenko"})


@pytest.fixture
def client(app):
    return app.test_client()


def get_csrf(client, path="/login"):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def login(client, username, password):
    token = get_csrf(client)
    return client.post("/login", data={"username": username, "password": password,
                                       "csrf_token": token})
