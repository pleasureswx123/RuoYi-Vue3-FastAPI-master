"""固定项目创建者身份，不以可变账号名称作为运行时保护依据。"""

import sqlalchemy as sa
from alembic import op

revision = '20261012_38'
down_revision = '20261012_37'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.execute('LOCK TABLE sg_project IN ACCESS EXCLUSIVE MODE')
    op.add_column('sg_project', sa.Column('creator_user_id', sa.BigInteger(), nullable=True))
    # 只确认创建时已经加入项目的唯一同名账号，无法确认的历史记录保持为空，不能猜测身份。
    op.execute("""
        UPDATE sg_project p SET creator_user_id = candidates.user_id
        FROM (
            SELECT p.project_id, min(u.user_id) AS user_id
            FROM sg_project p
            JOIN sys_user u ON u.user_name = p.create_by
            JOIN sg_project_member m ON m.project_id = p.project_id AND m.user_id = u.user_id
            WHERE p.create_by <> '' AND m.create_time <= p.create_time
            GROUP BY p.project_id HAVING count(*) = 1
        ) candidates WHERE p.project_id = candidates.project_id
    """)
    # 不擅自恢复旧成员或授予角色；历史不一致必须先人工核对，整个迁移可事务回滚。
    invalid = (
        op.get_bind()
        .execute(
            sa.text("""
        SELECT count(*) FROM sg_project p
        WHERE p.del_flag = '0' AND p.creator_user_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM sg_project_member m JOIN sg_project_member_role r
            ON r.project_id = m.project_id AND r.user_id = m.user_id
            WHERE m.project_id = p.project_id AND m.user_id = p.creator_user_id
              AND m.member_status = 'active' AND r.project_role = 'director'
        )
    """)
        )
        .scalar_one()
    )
    if invalid:
        raise RuntimeError('历史创建者已被移除或缺少管理人角色，请核对后重试迁移；未自动授权')
    op.execute("COMMENT ON COLUMN sg_project.creator_user_id IS '固定项目创建者用户ID，历史无法确认时为空'")


def downgrade() -> None:
    if op.get_context().dialect.name == 'postgresql':
        op.drop_column('sg_project', 'creator_user_id')
