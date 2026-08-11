from pathlib import Path

ROOT = Path(__file__).parents[2] / 'module_shot_grid'


def test_no_candidate_and_multiple_candidates_are_returned_without_guessing() -> None:
    dao = (ROOT / 'dao/requirement_dao.py').read_text()
    service = (ROOT / 'service/requirement_service.py').read_text()
    assert "'rows':" in service and "'total': total" in service
    assert 'description' not in dao.split('async def candidates', 1)[1]
    assert 'asset_name.ilike' in dao


def test_cross_project_wrong_type_and_archived_asset_are_excluded() -> None:
    service = (ROOT / 'service/requirement_service.py').read_text()
    assert 'ShotGridAsset.project_id == project_id' in service
    assert 'ShotGridAsset.asset_type == requirement.asset_type' in service
    assert "ShotGridAsset.lifecycle_status == 'active'" in service
    assert "ShotGridAsset.del_flag == '0'" in service
    assert "'SG_REQUIREMENT_CANDIDATE_INVALID'" in service


def test_duplicate_and_concurrent_resolution_use_atomic_optimistic_lock() -> None:
    dao = (ROOT / 'dao/requirement_dao.py').read_text()
    service = (ROOT / 'service/requirement_service.py').read_text()
    assert 'ShotGridShotAssetRequirement.lock_version == lock_version' in dao
    assert "resolution_status.in_(['pending', 'conflict'])" in dao
    assert 'lock_version=ShotGridShotAssetRequirement.lock_version + 1' in dao
    assert "shot_grid_error(409, 'SG_REQUIREMENT_VERSION_CONFLICT'" in service


def test_binding_and_audit_are_committed_together() -> None:
    service = (ROOT / 'service/requirement_service.py').read_text()
    resolve = service.index('ShotGridRequirementDao.resolve')
    relation = service.index('ShotGridRequirementDao.add_link_if_missing')
    commit = service.index('await db.commit()', relation)
    assert resolve < relation < commit
    assert "'resolved_by': user_id" in service
    assert "'update_by': username" in service
