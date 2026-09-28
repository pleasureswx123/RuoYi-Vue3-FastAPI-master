"""允许集号 0 表示可选预告片，保留已有集号和目录快照。"""

import sqlalchemy as sa
from alembic import op

revision = '20260928_35'
down_revision = '20260928_34'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.drop_constraint('ck_sg_episode_no', 'sg_episode', type_='check')
    op.create_check_constraint('ck_sg_episode_no', 'sg_episode', 'episode_no >= 0')


def downgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.execute('LOCK TABLE sg_episode IN ACCESS EXCLUSIVE MODE')
    if op.get_bind().execute(sa.text('SELECT 1 FROM sg_episode WHERE episode_no = 0 LIMIT 1')).first():
        raise RuntimeError('已有预告片集 EP000，禁止降级；请保留数据并继续使用当前版本')
    op.drop_constraint('ck_sg_episode_no', 'sg_episode', type_='check')
    op.create_check_constraint('ck_sg_episode_no', 'sg_episode', 'episode_no > 0')
