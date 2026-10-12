"""项目成员多角色关系及旧数据回填。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP

revision = '20261012_37'
down_revision = '20260930_36'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.execute('LOCK TABLE sg_project_member IN SHARE ROW EXCLUSIVE MODE')
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table('sg_project_member_role'):
        op.execute('LOCK TABLE sg_project_member_role IN SHARE ROW EXCLUSIVE MODE')
        _validate_existing_table(inspector)
    else:
        op.create_table(
            'sg_project_member_role',
            sa.Column('project_id', sa.BigInteger(), primary_key=True),
            sa.Column('user_id', sa.BigInteger(), primary_key=True),
            sa.Column('project_role', sa.String(20), primary_key=True),
            sa.Column('create_by', sa.String(64), nullable=False, server_default=''),
            sa.Column('create_time', TIMESTAMP(precision=0, timezone=False), nullable=False),
            sa.ForeignKeyConstraint(
                ['project_id', 'user_id'],
                ['sg_project_member.project_id', 'sg_project_member.user_id'],
                name='fk_sg_member_role_member',
                ondelete='RESTRICT',
            ),
            sa.CheckConstraint("project_role in ('director', 'creator')", name='ck_sg_member_role'),
            comment='项目成员角色关联表',
        )
        op.create_index(
            'idx_sg_member_role_project_role', 'sg_project_member_role', ['project_id', 'project_role', 'user_id']
        )
    op.execute("""INSERT INTO sg_project_member_role (project_id, user_id, project_role, create_by, create_time)
                  SELECT m.project_id, m.user_id, m.project_role, m.create_by, m.create_time FROM sg_project_member m
                  WHERE NOT EXISTS (SELECT 1 FROM sg_project_member_role r
                                    WHERE r.project_id=m.project_id AND r.user_id=m.user_id)""")


def _validate_existing_table(inspector: sa.Inspector) -> None:
    """允许 ORM 已提前创建的同构表，拒绝把未知结构当成已完成迁移。"""
    table = 'sg_project_member_role'
    columns = {column['name']: column for column in inspector.get_columns(table)}
    expected = {
        'project_id': sa.BigInteger(),
        'user_id': sa.BigInteger(),
        'project_role': sa.String(20),
        'create_by': sa.String(64),
        'create_time': TIMESTAMP(precision=0, timezone=False),
    }
    compatible = columns.keys() == expected.keys() and all(
        not columns[name]['nullable']
        and str(columns[name]['type'].compile(dialect=op.get_bind().dialect))
        == str(kind.compile(dialect=op.get_bind().dialect))
        for name, kind in expected.items()
    )
    compatible = compatible and inspector.get_pk_constraint(table)['constrained_columns'] == [
        'project_id',
        'user_id',
        'project_role',
    ]
    compatible = compatible and any(
        fk['constrained_columns'] == ['project_id', 'user_id']
        and fk['referred_table'] == 'sg_project_member'
        and fk['referred_columns'] == ['project_id', 'user_id']
        and fk.get('options', {}).get('ondelete') == 'RESTRICT'
        for fk in inspector.get_foreign_keys(table)
    )
    compatible = compatible and any(
        check['name'] == 'ck_sg_member_role' and "'director'" in check['sqltext'] and "'creator'" in check['sqltext']
        for check in inspector.get_check_constraints(table)
    )
    compatible = compatible and any(
        index['name'] == 'idx_sg_member_role_project_role'
        and index['column_names'] == ['project_id', 'project_role', 'user_id']
        for index in inspector.get_indexes(table)
    )
    if not compatible:
        raise RuntimeError('已存在的 sg_project_member_role 结构不兼容，拒绝回填及标记迁移完成')


def downgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.execute('LOCK TABLE sg_project_member, sg_project_member_role IN ACCESS EXCLUSIVE MODE')
    invalid = (
        op.get_bind()
        .execute(
            sa.text("""
        SELECT 1 FROM sg_project_member m LEFT JOIN sg_project_member_role r USING (project_id, user_id)
        GROUP BY m.project_id, m.user_id HAVING count(r.project_role) <> 1 LIMIT 1
    """)
        )
        .first()
    )
    if invalid:
        raise RuntimeError('存在多角色或缺失角色的项目成员，禁止降级丢失角色')
    op.execute("""UPDATE sg_project_member m SET project_role = r.project_role FROM sg_project_member_role r
                  WHERE m.project_id = r.project_id AND m.user_id = r.user_id""")
    op.drop_table('sg_project_member_role')
