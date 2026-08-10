from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_resource_controller_registers_complete_crud_and_archive_contract() -> None:
    source = (BACKEND_ROOT / 'module_shot_grid/controller/resource_controller.py').read_text(encoding='utf-8')
    for resource in ('episode', 'scene', 'shot', 'asset', 'assetItem'):
        assert f"_register_resource('{resource}'" in source
    for method in ("methods=['GET']", "methods=['POST']", "methods=['PUT']"):
        assert method in source
    assert 'ProjectAccessDependency' in source
    assert 'UserInterfaceAuthDependency' in source


def test_writes_are_project_scoped_and_optimistically_locked() -> None:
    dao = (BACKEND_ROOT / 'module_shot_grid/dao/resource_dao.py').read_text(encoding='utf-8')
    service = (BACKEND_ROOT / 'module_shot_grid/service/resource_service.py').read_text(encoding='utf-8')
    assert 'model.project_id == project_id' in dao
    assert 'model.lock_version == lock_version' in dao
    assert 'lock_version=model.lock_version + 1' in dao
    assert 'SG_LOCK_VERSION_CONFLICT' in service
    assert 'SG_RESOURCE_PROJECT_MISMATCH' in service
    assert "'del_flag': '0'" in service


def test_postgresql_business_constraints_remain_in_do_and_baseline() -> None:
    project_do = (BACKEND_ROOT / 'module_shot_grid/entity/do/project_do.py').read_text(encoding='utf-8')
    asset_do = (BACKEND_ROOT / 'module_shot_grid/entity/do/asset_do.py').read_text(encoding='utf-8')
    baseline = (BACKEND_ROOT / 'sql/ruoyi-fastapi-pg.sql').read_text(encoding='utf-8')
    for constraint in ('uk_sg_episode_no_active', 'uk_sg_scene_no_active', 'uk_sg_shot_no_active'):
        assert constraint in project_do
        assert constraint in baseline
    for constraint in ('uk_sg_asset_name_active', 'uk_sg_asset_item_name_active'):
        assert constraint in asset_do
        assert constraint in baseline
