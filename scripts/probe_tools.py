from app.infra.llm import get_chat_model
from langchain_core.tools import tool

@tool
def get_time() -> str:
    """查询当前时间"""
    return "22:47"

llm = get_chat_model().bind_tools([get_time])
r = llm.invoke("现在几点了？")
print("tool_calls =", r.tool_calls)
print("content    =", r.content)