from typing import Any

from sqlalchemy import func

# PostgreSQL btrim 与分配校验 str.strip 使用相同的空白字符集合。
ASSIGNMENT_WHITESPACE = ''.join(chr(code) for code in range(0x3100) if chr(code).isspace())


def missing_shot_content_expression(shot: Any) -> Any:
    return func.btrim(func.coalesce(shot.description, ''), ASSIGNMENT_WHITESPACE) == ''
