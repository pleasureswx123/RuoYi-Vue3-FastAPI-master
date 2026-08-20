"""增加 Shot Grid 受管平台用户角色来源表。

Revision ID: 20260818_12
Revises: 20260817_11
Create Date: 2026-08-18

本迁移只建立来源标记，不创建或猜测 ``shotgrid_admin`` / ``shotgrid_creator``
权限包。专用角色由平台管理端显式配置，业务写链对缺失或危险配置失败关闭。
"""

from collections.abc import Sequence

from alembic import op

revision: str = '20260818_12'
down_revision: str | Sequence[str] | None = '20260817_11'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == 'postgresql'


def upgrade() -> None:
    if not _is_postgresql():
        return

    op.execute(
        """
        CREATE TABLE sg_managed_user_role (
            user_id BIGINT NOT NULL,
            role_id BIGINT NOT NULL,
            create_by VARCHAR(64) DEFAULT '' NOT NULL,
            create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
            PRIMARY KEY (user_id, role_id),
            CONSTRAINT fk_sg_managed_user_role_user_role
                FOREIGN KEY (user_id, role_id)
                REFERENCES sys_user_role (user_id, role_id)
                ON DELETE CASCADE
        )
        """
    )
    op.execute("COMMENT ON TABLE sg_managed_user_role IS 'Shot Grid受管平台用户角色来源标记'")
    op.execute("COMMENT ON COLUMN sg_managed_user_role.user_id IS '平台用户ID'")
    op.execute("COMMENT ON COLUMN sg_managed_user_role.role_id IS '平台角色ID'")
    op.execute("COMMENT ON COLUMN sg_managed_user_role.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN sg_managed_user_role.create_time IS '创建时间'")


def downgrade() -> None:
    if not _is_postgresql():
        return
    op.execute(
        """
        DELETE FROM sys_user_role AS user_role
        USING sg_managed_user_role AS managed
        WHERE user_role.user_id = managed.user_id
          AND user_role.role_id = managed.role_id
        """
    )
    op.execute('DROP TABLE sg_managed_user_role')
