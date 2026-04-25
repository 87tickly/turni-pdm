"""Test bcrypt hash + verify (Sprint 2.1)."""

from colazione.auth.password import hash_password, verify_password


def test_hash_is_string_and_different_from_plain() -> None:
    plain = "mySecret123"
    hashed = hash_password(plain)
    assert isinstance(hashed, str)
    assert hashed != plain
    assert hashed.startswith("$2")  # bcrypt prefix


def test_hash_is_random_per_call() -> None:
    """Salt random → due hash della stessa password sono diversi."""
    h1 = hash_password("same-password")
    h2 = hash_password("same-password")
    assert h1 != h2


def test_verify_correct_password() -> None:
    plain = "ciaoBella2026"
    assert verify_password(plain, hash_password(plain)) is True


def test_verify_wrong_password() -> None:
    correct = "rightOne"
    wrong = "wrongOne"
    h = hash_password(correct)
    assert verify_password(wrong, h) is False


def test_verify_returns_false_for_malformed_hash() -> None:
    """Hash invalido → False, no eccezione."""
    assert verify_password("pwd", "not-a-bcrypt-hash") is False
    assert verify_password("pwd", "") is False
