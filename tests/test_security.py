"""身份令牌的签名/校验。

这块最容易写成"看起来能用"，所以把边界都钉死：伪造、篡改、空值、负数。
"""

import pytest

from app.core.security import sign_player, verify_player


def test_roundtrip():
    token = sign_player(42)
    assert verify_player(token) == 42


def test_token_format():
    pid, _, signature = sign_player(7).partition(".")
    assert pid == "7"
    assert len(signature) == 32


@pytest.mark.parametrize("bad", [None, "", "abc", "1.", ".abc", "0.abc", "-3.abc"])
def test_garbage_returns_none(bad):
    assert verify_player(bad) is None


def test_tampered_id_rejected():
    """把 id 从 42 改成 43，签名就对不上了。"""
    _, _, signature = sign_player(42).partition(".")
    assert verify_player(f"43.{signature}") is None


def test_tampered_signature_rejected():
    token = sign_player(42)
    pid, _, signature = token.partition(".")
    flipped = "A" if signature[0] != "A" else "B"
    assert verify_player(f"{pid}.{flipped}{signature[1:]}") is None


def test_different_players_differ():
    assert sign_player(1) != sign_player(2)