"""工具调用的重试策略。

两条边界：
1. 可重试的错误（超时/连接）→ 重试到上限后放弃
2. 不可重试的错误（参数错）→ **一次都不重试**，立刻上抛
"""

import asyncio

import pytest

from app.agents import nodes


class FlakyTool:
    """前 fail_times 次抛指定异常，之后返回 ok。"""

    def __init__(self, fail_times: int, exc: type[Exception] = TimeoutError) -> None:
        self.calls = 0
        self.fail_times = fail_times
        self.exc = exc

    async def ainvoke(self, args: dict):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc("boom")
        return "ok"


@pytest.fixture(autouse=True)
def _no_delay(monkeypatch):
    """测试里不要真的等退避。"""
    monkeypatch.setattr(nodes, "TOOL_RETRY_BASE_DELAY", 0)


def test_retries_then_succeeds():
    tool = FlakyTool(fail_times=2)
    assert asyncio.run(nodes._invoke_with_retry(tool, "t", {})) == "ok"
    assert tool.calls == 3  # 1 次原始 + 2 次重试


def test_gives_up_after_limit():
    tool = FlakyTool(fail_times=99)
    with pytest.raises(TimeoutError):
        asyncio.run(nodes._invoke_with_retry(tool, "t", {}))
    assert tool.calls == nodes.TOOL_RETRY_TIMES + 1


def test_non_retryable_fails_fast():
    tool = FlakyTool(fail_times=99, exc=ValueError)
    with pytest.raises(ValueError):
        asyncio.run(nodes._invoke_with_retry(tool, "t", {}))
    assert tool.calls == 1