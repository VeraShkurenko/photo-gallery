from gallery import validation as v
from tests.conftest import JPG, PNG


def test_username_rules():
    assert v.validate_username("ab") == v.ERR_USERNAME
    assert v.validate_username("a" * 31) == v.ERR_USERNAME
    assert v.validate_username("Віра") == v.ERR_USERNAME
    assert v.validate_username("user name") == v.ERR_USERNAME
    assert v.validate_username("' OR 1=1 --") == v.ERR_USERNAME
    assert v.validate_username("vira_2026") is None
    assert v.validate_username("a" * 30) is None


def test_password_rules():
    assert v.validate_password("1234567") == v.ERR_PASSWORD_SHORT
    assert v.validate_password("12345678") is None


def test_title_and_description():
    assert v.validate_title("ab") == v.ERR_TITLE
    assert v.validate_title("x" * 101) == v.ERR_TITLE
    assert v.validate_title("Захід") is None
    assert v.validate_description("x" * 1001) == v.ERR_DESCRIPTION
    assert v.validate_description("x" * 1000) is None


def test_image_rules():
    assert v.validate_image("a.png", PNG)[0] is None
    assert v.validate_image("a.JPEG", JPG)[2] == "jpg"
    assert v.validate_image("a.gif", PNG)[0] == v.ERR_IMAGE          # формат
    assert v.validate_image("a.png", JPG)[0] == v.ERR_IMAGE          # підміна розширення
    assert v.validate_image("a.png", b"hello")[0] == v.ERR_IMAGE     # не картинка
    big = PNG + b"\x00" * (5 * 1024 * 1024)
    assert v.validate_image("a.png", big)[0] == v.ERR_IMAGE          # > 5 МБ
    webp = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 20
    assert v.validate_image("a.webp", webp)[0] is None
