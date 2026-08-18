"""修复媒体派生文件的业务引用类型。

Revision ID: 20260817_11
Revises: 20260814_10
Create Date: 2026-08-17

早期媒体 Worker 将版本引用误写为 ``shot_grid_version``，导致缩略图和代理文件
无法通过版本下载授权。本迁移只处理确实属于版本文件关系的错误引用。
"""

from collections.abc import Sequence

from alembic import op

revision: str = '20260817_11'
down_revision: str | Sequence[str] | None = '20260814_10'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == 'postgresql'


def upgrade() -> None:
    if not _is_postgresql():
        return

    # 先删除错误引用，避免主文件同时保留两套业务引用类型。
    op.execute(
        """
        DELETE FROM sys_file_reference AS reference
        USING sg_version_file AS version_file
        WHERE reference.file_id = version_file.file_id
          AND reference.business_type = 'shot_grid_version'
          AND reference.business_id = version_file.version_id::text
        """
    )
    # 为缩略图、代理文件及可能仅有错误引用的主文件补齐正式版本引用。
    op.execute(
        """
        INSERT INTO sys_file_reference (
            file_id,
            business_type,
            business_id,
            business_name,
            retention_expire_time,
            create_by,
            create_time
        )
        SELECT
            version_file.file_id,
            'shotgrid_version',
            version_file.version_id::text,
            NULL,
            NULL,
            'shot-grid-media-reference-repair',
            current_timestamp
        FROM sg_version_file AS version_file
        JOIN sys_file_info AS file_info ON file_info.file_id = version_file.file_id
        WHERE file_info.status = 'active'
          AND file_info.del_flag = '0'
          AND NOT EXISTS (
              SELECT 1
              FROM sys_file_reference AS existing
              WHERE existing.file_id = version_file.file_id
                AND existing.business_type = 'shotgrid_version'
                AND existing.business_id = version_file.version_id::text
          )
        """
    )


def downgrade() -> None:
    # 数据修复不可逆；降级不得重新制造会绕过正式下载授权的错误引用类型。
    return
