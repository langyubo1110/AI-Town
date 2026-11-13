"""add npc weekly_goal + document_chunks (文档 RAG)

Revision ID: b7c4d1e08a11
Revises: 8e4b10b2333a
Create Date: 2026-11-13 15:10:00.000000

两件事：
1. npcs.weekly_goal —— 让每日计划有目标可挂（A-3）
2. document_chunks —— 文档 RAG 的存储（C）
"""
from typing import Sequence, Union

import pgvector
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c4d1e08a11'
down_revision: Union[str, Sequence[str], None] = '8e4b10b2333a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ---- A-3：NPC 的周目标 ----
    # server_default="" 让已有数据行自动补空串，不需要单独写 UPDATE 回填
    op.add_column(
        'npcs',
        sa.Column('weekly_goal', sa.String(length=120), server_default='', nullable=False),
    )

    # ---- C：文档块 ----
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        'document_chunks',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('source', sa.String(length=128), nullable=False),
        sa.Column('chunk_index', sa.BigInteger(), nullable=False),
        sa.Column('title', sa.String(length=128), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_document_chunks')),
    )
    op.create_index(op.f('ix_document_chunks_source'), 'document_chunks', ['source'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_document_chunks_source'), table_name='document_chunks')
    op.drop_table('document_chunks')
    op.drop_column('npcs', 'weekly_goal')