import io

from tests.conftest import PNG, get_csrf, login


def test_footer_has_surname_and_hostname(client, app):
    html = client.get("/").get_data(as_text=True)
    assert f"Фотогалерея | Shkurenko | {app.hostname}" in html


def test_protected_pages_redirect_to_login(client):
    for path in ["/post/new", "/admin/moderation"]:
        r = client.get(path)
        assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_state_changing_routes_are_post_only(client):
    assert client.get("/logout").status_code == 405
    assert client.get("/post/1/like").status_code == 405
    assert client.get("/post/1/delete").status_code == 405


def test_post_without_csrf_rejected(client):
    r = client.post("/login", data={"username": "alice", "password": "alicepass123"})
    assert r.status_code == 400


def test_register_errors(client):
    token = get_csrf(client, "/register")
    r = client.post("/register", data={"username": "alice", "password": "longenough1", "csrf_token": token})
    assert "Таке ім&#39;я вже зайняте" in r.get_data(as_text=True)
    r = client.post("/register", data={"username": "x!", "password": "longenough1", "csrf_token": token})
    assert "Некоректне ім&#39;я користувача" in r.get_data(as_text=True)
    r = client.post("/register", data={"username": "newuser", "password": "short", "csrf_token": token})
    assert "Пароль занадто короткий" in r.get_data(as_text=True)


def test_bad_login_same_message_and_sql_injection(client):
    for user, pw in [("alice", "wrong-password"), ("nobody", "whatever1"), ("' OR '1'='1' -- ", "x")]:
        r = login(client, user, pw)
        assert "Невірний логін або пароль" in r.get_data(as_text=True)


def test_lockout_after_5_failures(client):
    for _ in range(5):
        assert "Невірний логін" in login(client, "alice", "bad-password").get_data(as_text=True)
    r = login(client, "alice", "alicepass123")  # навіть правильний пароль
    assert "Забагато спроб, спробуйте пізніше" in r.get_data(as_text=True)


def test_success_resets_counter(client, repo):
    for _ in range(4):
        login(client, "alice", "bad-password")
    assert login(client, "alice", "alicepass123").status_code == 302
    assert repo.get_login_state("alice") == (0, None)


def _new_post(client, title="Мій пост", data=PNG, name="p.png"):
    token = get_csrf(client, "/post/new")
    return client.post("/post/new", content_type="multipart/form-data", data={
        "title": title, "description": "опис", "category_id": "1", "csrf_token": token,
        "image": (io.BytesIO(data), name)})


def test_moderation_flow(client, repo, storage):
    login(client, "alice", "alicepass123")
    r = _new_post(client)
    assert r.status_code == 302
    pid = max(repo.posts)
    assert repo.posts[pid]["status"] == "pending"
    assert storage.objects  # файл завантажено в S3
    assert "Мій пост" not in client.get("/").get_data(as_text=True)
    client.post("/logout", data={"csrf_token": get_csrf(client, "/")})
    login(client, "admin", "adminpass123")
    client.post(f"/admin/post/{pid}/approve", data={"csrf_token": get_csrf(client, "/")})
    assert "Мій пост" in client.get("/").get_data(as_text=True)


def test_admin_post_published_immediately(client, repo):
    login(client, "admin", "adminpass123")
    _new_post(client, title="Адмінський")
    assert repo.posts[max(repo.posts)]["status"] == "approved"


def test_invalid_image_and_title(client):
    login(client, "alice", "alicepass123")
    assert "Недопустимий файл зображення" in _new_post(client, data=b"not image").get_data(as_text=True)
    assert "Назва має містити від 3 до 100 символів" in _new_post(client, title="ab").get_data(as_text=True)


def test_user_cannot_approve(client, repo):
    login(client, "alice", "alicepass123")
    _new_post(client)
    pid = max(repo.posts)
    r = client.post(f"/admin/post/{pid}/approve", data={"csrf_token": get_csrf(client, "/")})
    assert r.status_code == 403 and repo.posts[pid]["status"] == "pending"


def test_delete_foreign_post_forbidden(client, repo, storage):
    login(client, "alice", "alicepass123")
    _new_post(client)
    pid = max(repo.posts)
    client.post("/logout", data={"csrf_token": get_csrf(client, "/")})
    login(client, "bob", "bobpass1234")
    r = client.post(f"/post/{pid}/delete", data={"csrf_token": get_csrf(client, "/")})
    assert r.status_code == 403
    assert pid in repo.posts and storage.objects


def test_author_deletes_post_and_file(client, repo, storage):
    login(client, "alice", "alicepass123")
    _new_post(client)
    pid = max(repo.posts)
    client.post(f"/post/{pid}/delete", data={"csrf_token": get_csrf(client, "/")})
    assert pid not in repo.posts and not storage.objects


def test_double_like_counts_once(client, repo):
    login(client, "admin", "adminpass123")
    _new_post(client, title="Лайкни")
    pid = max(repo.posts)
    token = get_csrf(client, "/")
    client.post(f"/post/{pid}/like", data={"csrf_token": token})
    client.post(f"/post/{pid}/like", data={"csrf_token": token})
    assert repo.get_post(pid)["likes"] == 1


def test_health_ok_and_fail(client, repo, storage, app):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok", "db": "ok", "s3": "ok", "host": app.hostname}
    repo.db_ok = False
    r = client.get("/health")
    assert r.status_code == 503 and r.get_json()["db"] == "fail"
    repo.db_ok, storage.ok = True, False
    r = client.get("/health")
    assert r.status_code == 503 and r.get_json()["s3"] == "fail"


def test_session_idle_timeout(client):
    login(client, "alice", "alicepass123")
    with client.session_transaction() as s:
        s["last_seen"] -= 31 * 60
    r = client.get("/post/new")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
