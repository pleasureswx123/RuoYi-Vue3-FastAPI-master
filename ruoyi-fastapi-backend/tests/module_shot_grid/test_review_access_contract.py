# ruff: noqa: ANN201, PLR2004
from pathlib import Path

ROOT = Path(__file__).parents[2] / 'module_shot_grid'


def test_creator_can_reply_but_cannot_create_or_review():
    source = (ROOT / 'controller' / 'review_controller.py').read_text(encoding='utf-8')
    assert "ProjectRoleDependency('director')" in source
    reply_block = source[source.index("'/{noteId}/replies'") : source.index('@review_controller.patch')]
    assert 'ProjectAccessDependency()' in reply_block
    assert 'ProjectRoleDependency' not in reply_block


def test_every_route_keeps_project_access_and_platform_permission():
    source = (ROOT / 'controller' / 'review_controller.py').read_text(encoding='utf-8')
    assert source.count('UserInterfaceAuthDependency') >= 5
    assert source.count('access: Annotated[ShotGridProjectAccessModel') == 4
