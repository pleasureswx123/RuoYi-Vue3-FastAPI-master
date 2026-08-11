"""第 13 节统计口径的真实 PostgreSQL 集成测试。

测试使用独立临时 schema，不依赖或改写开发库数据。通过
``SHOT_GRID_TEST_POSTGRES_URL`` 显式提供 asyncpg URL 后运行。
"""

import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from module_shot_grid.dao.discovery_dao import _member_projects
from module_shot_grid.dao.project_overview_dao import ShotGridProjectOverviewDao
from module_shot_grid.service.project_overview_service import ShotGridProjectOverviewService

pytestmark = pytest.mark.postgresql_integration


@pytest.fixture
async def pg_session() -> AsyncIterator[Any]:
    url = os.getenv('SHOT_GRID_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('未设置 SHOT_GRID_TEST_POSTGRES_URL，未执行真实 PostgreSQL 集成测试')
    schema = f'sg_overview_{uuid.uuid4().hex}'
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA {schema}'))
        await connection.execute(text(f'SET search_path TO {schema}'))
        await connection.execute(text(_SCHEMA_SQL))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text(f'SET search_path TO {schema}'))
        yield session
        await session.rollback()
    async with engine.begin() as connection:
        await connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
    await engine.dispose()


async def test_section_13_metrics_and_list_controls_do_not_change_totals(pg_session: AsyncSession) -> None:
    await pg_session.execute(text(_DATA_SQL))
    await pg_session.commit()

    baseline = await ShotGridProjectOverviewDao.get_overview(pg_session, 1)
    overview = ShotGridProjectOverviewService.build_model(baseline)
    assert overview.model_dump() == {
        'current_phase': 'shot_production',
        'total_episodes': 1,
        'total_scenes': 1,
        'total_shots': 6,
        'total_assets': 7,
        'total_asset_items': 6,
        'completed_shots': 1,
        'completed_assets': 1,
        'completed_asset_items': 1,
        'pending_review_shots': 1,
        'pending_review_assets': 1,
        'pending_review_asset_items': 1,
        'revision_shots': 1,
        'revision_assets': 1,
        'revision_asset_items': 1,
        'unassigned_shots': 1,
        'unassigned_assets': 2,
        'unassigned_asset_items': 1,
        'overall_progress': 16.7,
    }

    # 表格、卡片和故事板共享同一镜头分页结果；筛选和分页只作用于列表 SQL。
    for view, page_num, status in (('table', 1, None), ('cards', 2, None), ('storyboard', 1, 'revision')):
        await pg_session.execute(
            text(
                "SELECT shot_id FROM sg_shot WHERE project_id=1 AND del_flag='0' "
                "AND lifecycle_status='active' "
                + ('AND shot_id=5 ' if status == 'revision' else '')
                + 'ORDER BY shot_id LIMIT 2 OFFSET :offset'
            ),
            {'offset': (page_num - 1) * 2, 'view': view},
        )
        current = ShotGridProjectOverviewService.build_model(
            await ShotGridProjectOverviewDao.get_overview(pg_session, 1)
        )
        assert current == overview


async def test_archived_project_and_removed_member_are_not_discovery_scope(pg_session: AsyncSession) -> None:
    await pg_session.execute(text(_DATA_SQL))
    await pg_session.execute(
        text(
            'INSERT INTO sg_project_member VALUES '
            "(1, 10, 'director', 'active'), (2, 10, 'director', 'active'), (3, 10, 'director', 'removed')"
        )
    )
    project_ids = list((await pg_session.execute(_member_projects(10))).scalars())
    assert project_ids == [1]


_SCHEMA_SQL = """
CREATE TABLE sg_project (
 project_id bigint PRIMARY KEY, project_code varchar, project_name varchar, project_type varchar,
 project_description text, aspect_ratio varchar, planned_duration_ms bigint, delivery_date date,
 project_status varchar, current_phase varchar, create_by varchar, create_time timestamp,
 update_by varchar, update_time timestamp, remark varchar, lock_version int, del_flag char(1)
);
CREATE TABLE sg_project_member (
 project_id bigint, user_id bigint, project_role varchar, producer_code varchar, member_status varchar,
 joined_time timestamp, removed_by bigint, removed_time timestamp, create_by varchar, create_time timestamp
);
CREATE TABLE sg_episode (
 episode_id bigint PRIMARY KEY, project_id bigint, episode_no int, storage_dir_name varchar,
 episode_name varchar, description text, sort_order int, lifecycle_status varchar,
 create_by varchar, create_time timestamp, update_by varchar, update_time timestamp,
 remark varchar, lock_version int, del_flag char(1)
);
CREATE TABLE sg_scene (
 scene_id bigint PRIMARY KEY, project_id bigint, episode_id bigint, scene_no int, scene_name varchar,
 description text, sort_order int, lifecycle_status varchar, create_by varchar, create_time timestamp,
 update_by varchar, update_time timestamp, remark varchar, lock_version int, del_flag char(1)
);
CREATE TABLE sg_shot (
 shot_id bigint PRIMARY KEY, project_id bigint, episode_id bigint, scene_id bigint, shot_no int,
 storage_dir_name varchar, duration_ms bigint, shot_size varchar, camera_position varchar,
 camera_movement varchar, focal_length varchar, description text, dialogue text, sound_effect text,
 color_reference text, sort_order int, lifecycle_status varchar, create_by varchar, create_time timestamp,
 update_by varchar, update_time timestamp, remark varchar, lock_version int, del_flag char(1)
);
CREATE TABLE sg_asset (
 asset_id bigint PRIMARY KEY, project_id bigint, asset_name varchar, asset_name_key varchar,
 asset_type varchar, asset_code varchar, storage_dir_name varchar, storage_path_key varchar,
 description text, sort_order int, lifecycle_status varchar, create_by varchar, create_time timestamp,
 update_by varchar, update_time timestamp, remark varchar, lock_version int, del_flag char(1)
);
CREATE TABLE sg_asset_item (
 asset_item_id bigint PRIMARY KEY, project_id bigint, asset_id bigint, production_item varchar,
 production_item_key varchar, description text, sort_order int, source_import_batch_id bigint,
 source_row_no int, import_row_key char(64), lifecycle_status varchar, create_by varchar,
 create_time timestamp, update_by varchar, update_time timestamp, remark varchar,
 lock_version int, del_flag char(1)
);
CREATE TABLE sg_task (
 task_id bigint PRIMARY KEY, project_id bigint, shot_id bigint, asset_item_id bigint, task_name varchar,
 task_kind varchar, assignee_user_id bigint, task_status varchar, priority varchar, due_date date,
 requirements text, create_by varchar, create_time timestamp, update_by varchar, update_time timestamp,
 remark varchar, lock_version int, del_flag char(1)
);
CREATE TABLE sg_version (
 version_id bigint PRIMARY KEY, project_id bigint, task_id bigint, submission_id bigint,
 version_no int, version_status varchar, changelog text, ai_params jsonb, submitted_by bigint,
 submitted_time timestamp, generated_at_ms bigint, lock_version int
);
"""

_DATA_SQL = """
INSERT INTO sg_project (project_id,project_code,project_name,project_status,current_phase,del_flag)
VALUES (1,'ACTIVE','活动项目','active','shot_production','0'),
       (2,'ARCHIVE','归档项目','archived','delivery','0'),
       (3,'DELETED','删除项目','active','planning','2');
INSERT INTO sg_episode (episode_id,project_id,episode_no,storage_dir_name,sort_order,lifecycle_status,del_flag)
VALUES (1,1,1,'EP001',1,'active','0'),(2,1,2,'EP002',2,'archived','0'),(3,1,3,'EP003',3,'active','2');
INSERT INTO sg_scene (scene_id,project_id,episode_id,scene_no,sort_order,lifecycle_status,del_flag)
VALUES (1,1,1,1,1,'active','0'),(2,1,1,2,2,'archived','0'),(3,1,1,3,3,'active','2');
INSERT INTO sg_shot (shot_id,project_id,episode_id,scene_id,shot_no,storage_dir_name,duration_ms,description,sort_order,lifecycle_status,del_flag)
SELECT id,1,1,1,id,'SHOT'||id,1000,'状态镜头',id,'active','0' FROM generate_series(1,6) id;
INSERT INTO sg_shot (shot_id,project_id,episode_id,scene_id,shot_no,storage_dir_name,duration_ms,description,sort_order,lifecycle_status,del_flag)
VALUES (7,1,1,1,7,'SHOT7',1000,'归档',7,'archived','0'),(8,1,1,1,8,'SHOT8',1000,'删除',8,'active','2'),
       (9,1,1,2,9,'SHOT9',1000,'归档场次下镜头',9,'active','0');
INSERT INTO sg_asset (asset_id,project_id,asset_name,asset_name_key,asset_type,storage_dir_name,storage_path_key,sort_order,lifecycle_status,del_flag)
SELECT id,1,'资产'||id,'asset'||id,'Character','A'||id,'a/'||id,id,'active','0' FROM generate_series(1,7) id;
INSERT INTO sg_asset (asset_id,project_id,asset_name,asset_name_key,asset_type,storage_dir_name,storage_path_key,sort_order,lifecycle_status,del_flag)
VALUES (8,1,'归档资产','archived','Prop','A8','a/8',8,'archived','0'),(9,1,'删除资产','deleted','Prop','A9','a/9',9,'active','2');
INSERT INTO sg_asset_item (asset_item_id,project_id,asset_id,production_item,production_item_key,sort_order,lifecycle_status,del_flag)
SELECT id,1,id,'制作'||id,'item'||id,id,'active','0' FROM generate_series(1,6) id;
INSERT INTO sg_asset_item (asset_item_id,project_id,asset_id,production_item,production_item_key,sort_order,lifecycle_status,del_flag)
VALUES (7,1,1,'归档分项','archived',7,'archived','0'),(8,1,1,'删除分项','deleted',8,'active','2'),
       (9,1,8,'归档资产分项','parent-archived',9,'active','0');
INSERT INTO sg_task (task_id,project_id,shot_id,asset_item_id,task_name,task_kind,assignee_user_id,task_status,priority,del_flag)
VALUES (2,1,2,NULL,'未开始镜头','shot_video',10,'not_started','normal','0'),
 (3,1,3,NULL,'制作中镜头','shot_video',10,'in_progress','normal','0'),
 (4,1,4,NULL,'待审核镜头','shot_video',10,'pending_review','normal','0'),
 (5,1,5,NULL,'修改中镜头','shot_video',10,'revision','normal','0'),
 (6,1,6,NULL,'完成镜头','shot_video',10,'completed','normal','0'),
 (12,1,NULL,2,'未开始分项','asset_image',10,'not_started','normal','0'),
 (13,1,NULL,3,'制作中分项','asset_image',10,'in_progress','normal','0'),
 (14,1,NULL,4,'待审核分项','asset_image',10,'pending_review','normal','0'),
 (15,1,NULL,5,'修改中分项','asset_image',10,'revision','normal','0'),
 (16,1,NULL,6,'完成分项','asset_image',10,'completed','normal','0');
INSERT INTO sg_version (version_id,project_id,task_id,submission_id,version_no,version_status,changelog,submitted_by,submitted_time,generated_at_ms,lock_version)
VALUES (1,1,6,1,1,'final','完成',10,now(),1,0),(2,1,16,2,1,'final','完成',10,now(),2,0);
"""
