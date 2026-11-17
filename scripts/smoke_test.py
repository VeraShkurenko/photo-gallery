"""Наскрізна перевірка контракту (розділ 5) через балансувальник.
Використання:  ADMIN_PASSWORD=... python scripts/smoke_test.py http://<alb-dns>
Створює тимчасові пости й видаляє їх наприкінці."""
import os
import re
import struct
import sys
import uuid
import zlib

import requests

BASE = sys.argv[1].rstrip("/")
ADMIN_PW = os.environ["ADMIN_PASSWORD"]
ok_count = 0


def check(cond, msg):
    global ok_count
    print(("  OK  " if cond else "  FAIL") + " " + msg)
    if not cond:
        sys.exit(1)
    ok_count += 1


def png(w=40, h=30, rgb=(40, 120, 200)):
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def csrf(s, path="/"):
    return re.search(r'name="csrf_token" value="([^"]+)"', s.get(BASE + path).text).group(1)


def login(s, u, p):
    return s.post(BASE + "/login", data={"username": u, "password": p, "csrf_token": csrf(s, "/login")})


def new_post(s, title, data=None, name="t.png"):
    return s.post(BASE + "/post/new", data={"title": title, "description": "smoke test", "category_id": "1",
                                           "csrf_token": csrf(s, "/post/new")},
                  files={"image": (name, data if data is not None else png(), "image/png")})


print("health / hostnames")
hosts = set()
for _ in range(12):
    r = requests.get(BASE + "/health", timeout=10)
    j = r.json()
    check(r.status_code == 200 and j["db"] == j["s3"] == j["status"] == "ok", f"/health {j}") if not hosts else None
    hosts.add(j["host"])
check(len(hosts) == 2, f"ALB розподіляє на 2 web: {sorted(hosts)}")
foot = re.search(r'<footer class="footer">(.*?)</footer>', requests.get(BASE + "/").text).group(1)
check(foot.startswith("Фотогалерея | Shkurenko | ip-"), f"футер: {foot}")

suffix = uuid.uuid4().hex[:6]
u1, u2, pw = f"smoke_a_{suffix}", f"smoke_b_{suffix}", "SmokePass123"
a, b, adm, anon = requests.Session(), requests.Session(), requests.Session(), requests.Session()

print("auth")
r = anon.get(BASE + "/post/new", allow_redirects=False)
check(r.status_code == 302 and "/login" in r.headers["Location"], "неавторизований -> /login")
r = a.post(BASE + "/register", data={"username": "a!", "password": pw, "csrf_token": csrf(a, "/register")})
check("Некоректне ім&#39;я користувача" in r.text, "некоректне ім'я")
r = a.post(BASE + "/register", data={"username": u1, "password": "short", "csrf_token": csrf(a, "/register")})
check("Пароль занадто короткий" in r.text, "короткий пароль")
for s, u in [(a, u1), (b, u2)]:
    r = s.post(BASE + "/register", data={"username": u, "password": pw, "csrf_token": csrf(s, "/register")})
    check(u in r.text, f"реєстрація {u}")
r = anon.post(BASE + "/register", data={"username": u1, "password": pw, "csrf_token": csrf(anon, "/register")})
check("Таке ім&#39;я вже зайняте" in r.text, "дубль імені")
check("Невірний логін або пароль" in login(anon, "' OR '1'='1' -- ", "x").text, "SQL injection у логіні")
check("Невірний логін або пароль" in login(anon, u1, "wrongpassword").text, "невірний пароль")
check(anon.get(BASE + "/logout").status_code == 405, "GET /logout -> 405 (лише POST)")
check(anon.post(BASE + "/login", data={"username": u1, "password": pw}).status_code == 400, "POST без CSRF -> 400")
check(login(adm, "admin", ADMIN_PW).url.rstrip("/") == BASE, "вхід admin")

print("posts / moderation")
check("Недопустимий файл зображення" in new_post(a, "Bad file", b"GIF89a....", "x.gif").text, "недопустимий файл")
check("Недопустимий файл зображення" in new_post(a, "Too big", png() + b"\0" * (5 * 1024 * 1024 + 10)).text, "файл > 5 МБ")
check("Назва має містити від 3 до 100 символів" in new_post(a, "ab").text, "коротка назва")
r = new_post(a, f"Smoke pending {suffix}")
pid = int(re.search(r"/post/(\d+)", r.url).group(1))
check("pending" in r.text, f"пост користувача #{pid} pending")
check(f"Smoke pending {suffix}" not in anon.get(BASE + "/?q=" + suffix).text, "pending не видно на головній")
check(anon.get(f"{BASE}/post/{pid}").status_code == 404, "pending не видно анонімам")
check(b.post(f"{BASE}/admin/post/{pid}/approve", data={"csrf_token": csrf(b)}).status_code == 403, "user не може схвалити")
check(f"Smoke pending {suffix}" in adm.get(BASE + "/admin/moderation").text, "пост у /admin/moderation")
adm.post(f"{BASE}/admin/post/{pid}/approve", data={"csrf_token": csrf(adm)})
check(f"Smoke pending {suffix}" in anon.get(BASE + "/?q=" + suffix).text, "після схвалення є на головній")
page = anon.get(f"{BASE}/post/{pid}").text
img = re.search(r'<img class="full" src="([^"]+)"', page).group(1).replace("&amp;", "&")
check(img.startswith("https://gallery-shkurenko.s3.amazonaws.com/images/"), "зображення веде на S3")
check(requests.get(img).status_code == 200, "підписане посилання на S3 працює")
check(requests.get(img.split("?")[0]).status_code == 403, "без підпису бакет недоступний (приватний)")
r = new_post(adm, f"Smoke admin {suffix}")
apid = int(re.search(r"/post/(\d+)", r.url).group(1))
check(f"Smoke admin {suffix}" in anon.get(BASE + "/?q=" + suffix).text, "пост admin опубліковано одразу")

print("likes / comments / delete")
for _ in range(2):
    b.post(f"{BASE}/post/{pid}/like", data={"csrf_token": csrf(b)})
check("Лайків: <b>1</b>" in anon.get(f"{BASE}/post/{pid}").text, "подвійний лайк = +1")
b.post(f"{BASE}/post/{pid}/comment", data={"text": "Гарне фото!", "csrf_token": csrf(b)})
check("Гарне фото!" in anon.get(f"{BASE}/post/{pid}").text, "коментар")
r = b.post(f"{BASE}/post/{pid}/delete", data={"csrf_token": csrf(b)})
check(r.status_code == 403 and anon.get(f"{BASE}/post/{pid}").status_code == 200, "видалення чужого -> 403, пост на місці")
st = anon.get(BASE + "/stats").text
check(all(h in st for h in ["Топ-5 постів", "Пости по днях", "Топ-3 автори"]), "/stats три блоки")

print("lockout")
lu = f"smoke_lock_{suffix}"
s = requests.Session()
s.post(BASE + "/register", data={"username": lu, "password": pw, "csrf_token": csrf(s, "/register")})
s = requests.Session()
for i in range(5):
    login(s, lu, "wrong-pass")
check("Забагато спроб, спробуйте пізніше" in login(s, lu, pw).text, "6-та спроба (навіть з вірним паролем) заблокована")

print("cleanup")
check(a.post(f"{BASE}/post/{pid}/delete", data={"csrf_token": csrf(a)}).url.rstrip("/") == BASE, "автор видалив свій пост")
check(adm.post(f"{BASE}/post/{apid}/delete", data={"csrf_token": csrf(adm)}).status_code == 200, "admin видалив пост")
check(requests.get(img).status_code in (403, 404), "файл видалено з S3")
print(f"\nУСЕ ГАРАЗД: {ok_count} перевірок")
