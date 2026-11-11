"""SQLAlchemy 声明式基类。"""

from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

'''
提供所有数据库模型(表)继承的基类 Base 和公共字段混入类 TimestampMixin
'''

'''
约束命名约定：让 Postgres 自动生成的索引/约束名可预测
SQLAlchemy 的 命名模板,用来给数据库自动生成的约束/索引一个可预测、统一风格的名字
'''
NAMING_CONVENTION = {
    #index(普通索引)
    "ix": "ix_%(column_0_label)s",
    #unique constraint(唯一约束)
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    #check constraint(检查约束)
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    #foreign key(外键)
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    #primary key(主键)
    "pk": "pk_%(table_name)s",
}

#声明式基类
class Base(DeclarativeBase):
    #全局表注册中心,所有模型表都注册在这里，使用这套约束命名规则。
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

#时间基类
class TimestampMixin:
    """所有表都需要的创建/更新时间。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )