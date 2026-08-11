from pathlib import Path

from module_shot_grid.entity.vo.discovery_vo import ShotGridDiscoveryQueryModel


def test_search_query_normalizes_keyword_and_page_boundary() -> None:
    page_num, page_size = 2, 100
    query = ShotGridDiscoveryQueryModel(keyword='  cat  ', pageNum=page_num, pageSize=page_size, resourceType='file')
    assert query.keyword == 'cat'
    assert query.page_num == page_num
    assert query.page_size == page_size


def test_discovery_queries_apply_member_scope_and_stable_order() -> None:
    source = Path('module_shot_grid/dao/discovery_dao.py').read_text(encoding='utf-8')
    assert "member_status == 'active'" in source
    assert 'project_id.in_(member_projects)' in source
    assert 'resource_id.desc()' in source


def test_file_contract_uses_protected_download_and_server_side_path_redaction() -> None:
    source = Path('module_shot_grid/service/discovery_service.py').read_text(encoding='utf-8')
    assert "can_view_path = has_all_scope or role.scalar_one_or_none() == 'director'" in source
    assert "'/download'" not in source  # 下载地址必须携带完整项目、任务、版本和文件上下文
    assert '/files/{relation.file_id}/download' in source
