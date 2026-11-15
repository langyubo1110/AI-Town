"""会话：给玩家发一个签名过的身份 Cookie。

为什么单独开一个路由：
    其它接口都需要"我是谁"，但前端第一次打开页面时还没有身份。
    这个接口就是那一次握手：`POST /api/session {name}` → 建号（或取号）+ 下发 Cookie。
"""

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import _player_from_cookie, get_session
from app.core.security import COOKIE_MAX_AGE, COOKIE_NAME, sign_player
from app.repos import player_repo

router = APIRouter(tags=["session"])


class SessionIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=32)


class SessionOut(BaseModel):
    player_id: int
    name: str


@router.post("/session", response_model=SessionOut, summary="建立会话（下发身份 Cookie）")
async def create_session(
    payload: SessionIn,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> SessionOut:
    player = await player_repo.get_or_create_by_name(session, payload.name)
    await session.commit()

    response.set_cookie(
        key=COOKIE_NAME,
        value=sign_player(player.id),
        max_age=COOKIE_MAX_AGE,
        httponly=True,       # 前端 JS 拿不到，XSS 也偷不走
        samesite="lax",
        path="/",
    )
    return SessionOut(player_id=player.id, name=player.name)


@router.get("/me", response_model=SessionOut, summary="当前身份")
async def me(
    session: AsyncSession = Depends(get_session),
    player_id: int | None = Depends(_player_from_cookie),
) -> SessionOut:
    """只有拿着有效 Cookie 才回身份；没有就 401。"""
    from fastapi import HTTPException, status

    if player_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="尚未建立会话",
        )

    from app.models import Player

    player = await session.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="玩家不存在")
    return SessionOut(player_id=player.id, name=player.name)