# Скриншоти С1–С24: що й де фотографувати

**Загальні правила ТЗ:** кожен скриншот підписати номером (С1…С24); має бути видно адресний рядок
або повне вікно консолі; на кожному має бути видно прізвище. У консолі AWS прізвище видно у правому
верхньому куті (**ViraShkurenko**), на сайті у футері (**Shkurenko**). Робіть **повне вікно**
(⌘ + Shift + 4, потім Пробіл і клік по вікну), а не вирізаний фрагмент.

Корисні адреси:

| Що | Адреса |
|---|---|
| Сайт (ALB) | http://gallery-alb-shkurenko-375269311.us-east-1.elb.amazonaws.com/ |
| EC2 Instances | https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#Instances: |
| Security Groups | https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#SecurityGroups: |
| Load Balancers | https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#LoadBalancers: |
| Target Groups | https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#TargetGroups: |
| Роль web | https://us-east-1.console.aws.amazon.com/iam/home#/roles/details/gallery-web-role-shkurenko |
| Бакет | https://us-east-1.console.aws.amazon.com/s3/buckets/gallery-shkurenko?region=us-east-1 |

Hostname машин: **web-1 = `ip-172-31-31-198`**, **web-2 = `ip-172-31-29-7`**, db = `ip-172-31-31-149`.

## Як відкрити термінал на машині (у браузері, без ключів)

* **web-1 / web-2:** EC2 → Instances → виділити `web-1-Shkurenko` → кнопка **Connect** → вкладка
  **Session Manager** → **Connect**. Відкриється чорний термінал у браузері. Спершу введіть
  `sudo -i`, потім `cd /`.
* **db:** EC2 → Instances → `db-node-Shkurenko` → **Connect** → вкладка **EC2 Instance Connect** →
  вибрати **Connect using a Private IP** (або *EC2 Instance Connect Endpoint*), Endpoint `eice-shkurenko`,
  користувач `ubuntu` → **Connect**.
  Те саме з терміналу Mac: `~/photo-gallery/infra/db-shell.sh`.

Першим рядком у кожному терміналі вводьте `echo "Shkurenko"; hostname`, щоб прізвище було видно на скриншоті.

## Підготовка даних на сайті (≈10 хв, потрібна для С6, С12, С17–С23)

Пароль адміністратора можна подивитися в терміналі Mac (у чат його не пишіть):
```bash
aws ssm get-parameter --name /gallery/admin_password --with-decryption --query Parameter.Value --output text
```

1. Відкрийте сайт і **зареєструйте** двох користувачів, наприклад `vira` і `olena` (пароль ≥ 8 символів).
   Для другого користувача зручно взяти **приватне вікно** Safari/Chrome (⌘ + Shift + N), тоді
   обидва облікові записи будуть відкриті одночасно.
2. Під `admin` створіть 2–3 пости зі своїми фото (jpg/png/webp, до 5 МБ). Вони публікуються одразу.
3. Під `vira` створіть пост (він потрапить на модерацію). → **С18**
4. Під `olena` поставте кілька лайків різним постам і напишіть коментар.

---

## Консоль AWS

**С1. Список EC2.** EC2 → Instances. У пошук введіть `Shkurenko` і відфільтруйте *Instance state = running*.
Видно три машини `running`; у колонці **Public IPv4 address** у `db-node-Shkurenko` стоїть «–».

**С2. Вхідні правила SG db.** Security Groups → `db-sg` → вкладка **Inbound rules**.
Видно `MySQL/Aurora 3306 → sg-0217ef80b66c79e83 (web-sg)`. Друге правило `SSH 22 → eice-sg`
(адмінський доступ через Instance Connect Endpoint) — MySQL відкритий лише для web-sg.

**С3. Вхідні правила SG web.** Security Groups → `web-sg` → **Inbound rules**: одне правило
`HTTP 80 → sg-0c0724ea2b92352f4 (alb-sg)`.

**С4. ALB.** Load Balancers → `gallery-alb-shkurenko` → вкладка **Resource map**. На одному екрані видно
DNS name (зверху, у Details) і схему *Listener → gallery-tg-shkurenko → 2 targets **Healthy***.
Якщо не вміщується, зробіть С4а (Details з DNS) і С4б: Target Groups → `gallery-tg-shkurenko` →
**Targets** (обидва `Healthy`, видно health check `/health`).

**С5. Роль IAM на web і її політика S3.** (а) EC2 → `web-1-Shkurenko` → вкладка **Security**:
IAM Role = `gallery-web-role-shkurenko`. (б) IAM → Roles → `gallery-web-role-shkurenko` →
**Permissions** → розгорнути `gallery-web-role-shkurenko-policy` (кнопка **{} JSON**): видно, що доступ
лише до `arn:aws:s3:::gallery-shkurenko`.

**С6. Бакет.** S3 → `gallery-shkurenko` → вкладка **Objects** → папка `images/` (видно файли зображень).
Другий скрин: вкладка **Permissions** → *Block public access: **On*** (усі 4 пункти).

**С7. Бекап з датою.** S3 → `gallery-shkurenko` → `backups/` → видно файли
`gallery_2026-11-…sql.gz` (дата в назві й колонка *Last modified*).

## Термінал на db

**С8. Таблиці та структура posts з FK:**
```bash
echo "Shkurenko"; hostname
sudo mysql gallery -e "SHOW TABLES; SHOW CREATE TABLE posts\G"
```
Видно 7 таблиць і `CONSTRAINT fk_posts_user FOREIGN KEY … ON DELETE CASCADE`, `fk_posts_category`.

**С9. Паролі — хеші:**
```bash
sudo mysql gallery -e "SELECT id, username, role, password_hash, created_at FROM users"
```

**С10. Права користувача БД:**
```bash
sudo mysql -e "SELECT user, host, plugin FROM mysql.user; SHOW GRANTS FOR 'gallery'@'172.31.%';"
```
Видно: `gallery` має права лише на `gallery.*`; `root` лише `localhost` з `auth_socket`.
За бажанням додайте ще перевірку з web-1 (Session Manager): `mysql -h 172.31.31.149 -u root -p`
з будь-яким паролем дає `ERROR 1045 Access denied` / `Host … is not allowed`, тобто віддалений вхід
root неможливий.

**С12. action_log** (після того, як ви створили, схвалили й видалили пост на сайті):
```bash
sudo mysql gallery -e "SELECT * FROM action_log ORDER BY id"
```
Видно рядки `post_created`, `post_approved`, `post_deleted`. Їх записують тригери, код сайту в цю таблицю не пише.

**С13. Розклад автобекапу:**
```bash
systemctl list-timers gallery-backup.timer --no-pager
systemctl cat gallery-backup.timer --no-pager
```

## Термінал на web-1 (Session Manager)

**С11. Немає ключів AWS і паролів у коді й домашніх каталогах:**
```bash
echo "Shkurenko"; hostname
grep -rnE "AKIA[0-9A-Z]{16}|aws_secret_access_key" /opt/gallery /home /root --exclude-dir=.venv || echo "Ключів AWS немає"
ls -la /home/*/.aws/credentials /root/.aws/credentials 2>&1
P=$(grep ^DB_PASSWORD= /etc/gallery.env | cut -d= -f2-); grep -rlF "$P" /opt/gallery /home /root || echo "Пароль БД є лише в /etc/gallery.env"
ls -l /etc/gallery.env
```
Плюс другий скрин із **терміналу Mac** (перевірка репозиторію):
```bash
cd ~/photo-gallery && git grep -nE "AKIA|aws_secret|DB_PASSWORD=[^c{]" || echo "У репозиторії секретів немає"
```

**С14. Автостарт після перезавантаження.** EC2 → `web-1-Shkurenko` → *Instance state* → **Reboot**.
Через ~1 хв знову підключіться через Session Manager і виконайте:
```bash
echo "Shkurenko"; hostname; uptime -s; date; systemctl status gallery --no-pager | head -5
```
Поруч (у тому ж скриншоті, два вікна поряд) — сайт у браузері, оновлений, поки у футері не з'явиться
`ip-172-31-31-198`. Видно час запуску системи (`uptime -s`) і відкриту сторінку.

## Сайт

**С15.** Головна з футером, **два скрини**: оновлюйте сторінку (⌘R), поки у футері не з'явиться
`ip-172-31-31-198`, а потім `ip-172-31-29-7`.

**С16.** `…elb.amazonaws.com/health`: `{"status":"ok","db":"ok","s3":"ok","host":"ip-…"}`.

**С17.** Відкрийте пост → правий клік по фото → **Open Image in New Tab** → скрин нової вкладки:
адреса починається з `https://gallery-shkurenko.s3.amazonaws.com/images/…`.

**С18.** Під `vira` створіть пост (повідомлення про модерацію) → скрин головної, де його **немає**.
Під `admin` → **Модерація** → **Схвалити** → скрин головної, де пост **є** (2 скрини).

**С19.** Під `olena` відкрийте пост з 0 лайків → натисніть «♥ Подобається» **двічі** → скрин:
«Лайків: 1». Можна зробити два скрини: до (0) і після двох кліків (1).

**С20.** Під `olena` відкрийте пост `vira` → **Видалити** → підтвердити → сторінка
«Помилка 403 — Ви не можете видалити чужий пост. Пост не змінено.»

**С21.** Вийдіть → **Увійти** → логін `' OR '1'='1' -- ` і будь-який пароль → «Невірний логін або пароль».

**С22.** Логін `olena`, 5 разів неправильний пароль, на 6-й раз **правильний** пароль →
«Забагато спроб, спробуйте пізніше» (блокування на 15 хв).

**С23.** `/stats`: три блоки (топ-5 постів, пости по днях, топ-3 автори).

**С24. З власного комп'ютера.** У терміналі Mac:
```bash
~/photo-gallery/scripts/check_external.sh
```
Видно: у db немає публічної IP, порт 3306 недоступний, `curl` напряму на web — timeout, а через ALB `/health` = ok.
