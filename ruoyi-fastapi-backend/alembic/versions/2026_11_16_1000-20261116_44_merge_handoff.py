"""汇合主线与交接迁移，并对齐重新审核周期的约束名称。"""

from alembic import op

revision = '20261116_44'
down_revision = ('20261026_41', '20261111_43')
branch_labels = None
depends_on = None

CONSTRAINT_NAMES = (
    ('sg_review_cycle_cycle_no_check', 'ck_sg_review_cycle_no'),
    ('sg_review_cycle_outcome_check', 'ck_sg_review_cycle_outcome'),
)


def _rename_constraints(pairs: tuple[tuple[str, str], ...]) -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    for old, new in pairs:
        # 名称仅来自本迁移固定常量；兼容由 ORM 预建且已使用正式名称的空表。
        op.execute(f"""
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='sg_review_cycle'::regclass AND conname='{old}')
 AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='sg_review_cycle'::regclass AND conname='{new}') THEN
  ALTER TABLE sg_review_cycle RENAME CONSTRAINT {old} TO {new};
 END IF;
END $$;
""")


def upgrade() -> None:
    """保留两侧迁移身份，只规范约束名称，不改写业务数据。"""
    _rename_constraints(CONSTRAINT_NAMES)


def downgrade() -> None:
    """还原旧约束名称并拆分版本标记，不删除业务数据。"""
    _rename_constraints(tuple((new, old) for old, new in CONSTRAINT_NAMES))
