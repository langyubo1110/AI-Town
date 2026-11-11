"""
应用配置：所有环境变量的唯一入口。
环境变量的唯一入口（Settings + get_settings）
"""

#Python 内置缓存装饰器，用来实现单例
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（app/core/config.py → 上两级 = ai-town/）
BASE_DIR = Path(__file__).resolve().parents[2]

#pydantic 自动映射
class Settings(BaseSettings):
    #配置类的行为
    model_config = SettingsConfigDict(
        # 自动读.env
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        # .env 里有不认识的变量时不报错
        extra="ignore",
        # PORT=8000 能自动映射到 port: int，大小写不用管
        case_sensitive=False,
    )

    # ---- 应用 ----
    app_name: str = "AI Town"
    app_version: str = "0.1.0"
    env: str = "dev"
    debug: bool = True

    # ---- 服务器 ----
    host: str = "0.0.0.0"
    port: int = 8000
    #跨域地址
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---- LLM ----
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_timeout:int=60

    # ---- 存储 ----
    postgres_dsn: str = "postgresql+asyncpg://aitown:aitown@localhost:5432/aitown"
    redis_url: str = "redis://localhost:6379/0"
    db_pool_size: int = 5
    db_echo: bool = False  # 设为 true 会打印所有 SQL，调试用

    # ---- Embedding ----
    embed_api_key: str = ""
    embed_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embed_model: str = "text-embedding-v3"
    embed_dim: int = 1024

    # ---- 小镇自主行为 ----
    npc_tick_enabled: bool = True
    npc_tick_seconds: int = 60         # 每 60 秒触发一次
    npc_tick_max_backlog: int = 20     # 队列积压超过这个数就不再投递

    # ---- 可观测（Langfuse）：两个 key 都不填就自动关闭 ----
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    

    #方法返回值作为类的属性 可以访问
    @property
    #因为环境变量只能是字符串，但 FastAPI 的 CORS 中间件需要列表
    #分割域地址
    def cors_origin_list(self) -> list[str]:
        """把逗号分隔的字符串转成列表。"""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


# 缓存
#Settings() 每次实例化都会重新读 .env + 解析环境变量，有 I/O 开销
#加了 lru_cache 后，第一次调用后结果被缓存，之后永远返回同一个对象 → 变成单例
#单例 = 一个类在整个程序运行期间，只允许存在唯一一个实例（对象）。无论调用多少次，拿到的都是同一个实例对象
@lru_cache
def get_settings() -> Settings:
    return Settings()
