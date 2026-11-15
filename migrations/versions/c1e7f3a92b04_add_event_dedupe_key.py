"""add events.dedupe_key（幂等键）

Revision ID: c1e7f3a92b04
Revises: b7c4d1e08a11
Create Date: 2026-11-15 13:05:00.000000

为什么需要：
    Redis Stream 是"至少一次"语义 —— worker 崩了，pending 里的消息会被重投。
    没有幂等键时，同一条消息处理两次就写两条一模一样的事件，用户会看到
    两条"张三和李四聊了聊"。

为什么用"部分唯一索引"：
    历史数据没有幂等键（NULL），全表唯一约束会让多行 NULL 冲突。
    postgresql_where 把约束限定在"有键的行"，老数据完全不受影响。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1e7f3a92b04'
down_revision: Union[str, Sequence[str], None] = 'b7c4d1e08a11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'events', sa.Column('dedupe_key', sa.String(length=96), nullable=True)
    )
    op.create_index(
        'uq_events_dedupe_key',
        'events',
        ['dedupe_key'],
        unique=True,
        postgresql_where=sa.text('dedupe_key IS NOT NULL'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_events_dedupe_key', table_name='events')
    op.drop_column('events', 'dedupe_key')