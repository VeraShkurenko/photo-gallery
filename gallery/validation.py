"""Правила валідації (розділ 5.4 ТЗ). Тексти помилок — точно як у ТЗ."""
import re

ERR_USERNAME = "Некоректне ім'я користувача"
ERR_USERNAME_TAKEN = "Таке ім'я вже зайняте"
ERR_PASSWORD_SHORT = "Пароль занадто короткий"
ERR_BAD_LOGIN = "Невірний логін або пароль"
ERR_TOO_MANY = "Забагато спроб, спробуйте пізніше"
ERR_TITLE = "Назва має містити від 3 до 100 символів"
ERR_DESCRIPTION = "Опис занадто довгий"
ERR_IMAGE = "Недопустимий файл зображення"
ERR_CATEGORY = "Оберіть категорію"
ERR_COMMENT = "Коментар має містити від 1 до 1000 символів"

USERNAME_RE = re.compile(r"[A-Za-z0-9_]{3,30}")
MAX_IMAGE_BYTES = 5 * 1024 * 1024

# розширення -> (MIME, функція перевірки сигнатури файлу)
ALLOWED_IMAGES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def validate_username(username: str):
    if not username or not USERNAME_RE.fullmatch(username):
        return ERR_USERNAME
    return None


def validate_password(password: str):
    if password is None or len(password) < 8:
        return ERR_PASSWORD_SHORT
    return None


def validate_title(title: str):
    title = (title or "").strip()
    if not 3 <= len(title) <= 100:
        return ERR_TITLE
    return None


def validate_description(description: str):
    if len(description or "") > 1000:
        return ERR_DESCRIPTION
    return None


def validate_comment(text: str):
    text = (text or "").strip()
    if not 1 <= len(text) <= 1000:
        return ERR_COMMENT
    return None


def sniff_image_type(data: bytes):
    """Визначає реальний тип файлу за сигнатурою (а не за назвою)."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_image(filename: str, data: bytes):
    """Повертає (помилка, mime, розширення)."""
    if not filename or "." not in filename or not data:
        return ERR_IMAGE, None, None
    ext = filename.rsplit(".", 1)[1].lower()
    expected_mime = ALLOWED_IMAGES.get(ext)
    if expected_mime is None or len(data) > MAX_IMAGE_BYTES:
        return ERR_IMAGE, None, None
    if sniff_image_type(data) != expected_mime:
        return ERR_IMAGE, None, None
    return None, expected_mime, "jpg" if ext == "jpeg" else ext
