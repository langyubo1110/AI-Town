"""玩家身份的签名令牌（不引入 JWT，够用就行）。

问题：原来 `player_id` 完全由前端传（`?player_id=1`），
等于谁都能读别人的事件、冒充别人聊天。演示无所谓，上线就是洞。

方案：服务端把 `player_id` 用 HMAC-SHA256 签名后放进 **HttpOnly Cookie**，
之后以 Cookie 为准，前端传的 `player_id` 只作为"没有 Cookie 时"的兼容回退。

为什么不用 JWT：
    这里只有"是不是我签发的一个整数"这一个问题，不需要声明、过期、算法协商。
    HMAC + base64 二十行就能写完，还能直接单测。
"""

import base64
import hashlib
import hmac
from typing import Final

from app.core.config import get_settings

COOKIE_NAME: Final = "aitown_player"
COOKIE_MAX_AGE: Final = 60 * 60 * 24 * 30  # 30 天


def _secret() -> bytes:
    """签名密钥。默认值只适合本地开发，生产必须用 APP_SECRET 覆盖。"""
    return get_settings().app_secret.encode("utf-8")


def _sign(pid: int) -> str:
    """对 player_id 做 HMAC，返回 base64url 短签名。"""
    digest = hmac.new(_secret(), str(pid).encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")[:32]


def sign_player(pid: int) -> str:
    """生成 `{pid}.{sig}` 形式的令牌。"""
    return f"{pid}.{_sign(pid)}"


def verify_player(token: str | None) -> int | None:
    """校验令牌，返回 player_id；任何异常都当作"无效"。

    用 `hmac.compare_digest` 而不是 `==`：避免按字节比较泄露信息（时序攻击）。
    """
    if not token or "." not in token:
        return None

    raw_id, _, signature = token.partition(".")
    try:
        pid = int(raw_id)
    except ValueError:
        return None
    if pid <= 0:
        return None

    if not hmac.compare_digest(signature, _sign(pid)):
        return None
    return pid