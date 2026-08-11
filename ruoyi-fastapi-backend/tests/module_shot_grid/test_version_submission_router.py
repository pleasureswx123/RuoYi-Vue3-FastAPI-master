from fastapi import FastAPI

from common.aspect.interface_auth import CheckUserInterfaceAuth
from config.env import UploadConfig
from module_shot_grid.controller.version_submission_controller import version_submission_controller

VERSION_SUBMISSION_ROUTER_ORDER = 48
SQL_BIGINT_MAX = 9_223_372_036_854_775_807

EXPECTED_ROUTES = {
    ('POST', '/shot-grid/tasks/{taskId}/version-submissions'): 'shotgrid:version:add',
    ('GET', '/shot-grid/version-submissions/{submissionId}'): 'shotgrid:version:query',
    ('POST', '/shot-grid/version-submissions/{submissionId}/retry'): 'shotgrid:version:retry',
    ('GET', '/shot-grid/versions/{versionId}/files/{fileId}/download'): 'shotgrid:file:download',
}


def test_version_submission_routes_and_permissions_match_contract() -> None:
    actual = {}
    for route in version_submission_controller.routes:
        permissions = [
            dependency.dependency.perm
            for dependency in route.dependencies
            if isinstance(dependency.dependency, CheckUserInterfaceAuth)
        ]
        assert len(permissions) == 1
        for method in route.methods:
            actual[(method, route.path)] = permissions[0]

    assert version_submission_controller.order_num == VERSION_SUBMISSION_ROUTER_ORDER
    assert actual == EXPECTED_ROUTES


def test_version_submission_openapi_documents_business_required_header_and_bigint_bound() -> None:
    app = FastAPI()
    app.include_router(version_submission_controller)
    operation = app.openapi()['paths']['/shot-grid/tasks/{taskId}/version-submissions']['post']

    idempotency = next(parameter for parameter in operation['parameters'] if parameter['name'] == 'X-Idempotency-Key')
    assert idempotency['required'] is False
    assert '业务必填' in idempotency['description']
    task_id = next(parameter for parameter in operation['parameters'] if parameter['name'] == 'taskId')
    assert task_id['schema']['exclusiveMinimum'] == 0
    assert task_id['schema']['maximum'] == SQL_BIGINT_MAX
    assert '202' in operation['responses']


def test_platform_upload_allowlist_contains_mov_for_shot_versions() -> None:
    assert {'mp4', 'mov'} <= set(UploadConfig.DEFAULT_ALLOWED_EXTENSION)
