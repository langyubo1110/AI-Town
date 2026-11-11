"""领域异常。"""


class DomainError(Exception):
    """所有领域异常的基类。"""


class NPCNotFoundError(DomainError):
    """NPC 不存在或已下线。"""