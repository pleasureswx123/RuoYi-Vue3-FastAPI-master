from fastapi import FastAPI

from common.aspect.interface_auth import CheckUserInterfaceAuth
from module_shot_grid.controller.review_controller import review_controller

REVIEW_ROUTER_ORDER = 47
SQL_BIGINT_MAX = 9_223_372_036_854_775_807

EXPECTED_ROUTES = {
    ('GET', '/shot-grid/review-lists/mine'): 'shotgrid:reviewList:list',
    ('GET', '/shot-grid/versions/mine/recent'): 'shotgrid:version:list',
    ('GET', '/shot-grid/tasks/{taskId}/versions'): 'shotgrid:version:list',
    ('GET', '/shot-grid/versions/{versionId}'): 'shotgrid:version:query',
    ('GET', '/shot-grid/projects/{projectId}/review-lists'): 'shotgrid:reviewList:list',
    ('POST', '/shot-grid/projects/{projectId}/review-lists'): 'shotgrid:reviewList:add',
    ('GET', '/shot-grid/review-lists/{reviewListId}'): 'shotgrid:reviewList:query',
    ('PUT', '/shot-grid/review-lists/{reviewListId}'): 'shotgrid:reviewList:edit',
    ('POST', '/shot-grid/review-lists/{reviewListId}/versions'): 'shotgrid:reviewList:edit',
    ('DELETE', '/shot-grid/review-lists/{reviewListId}/versions/{versionId}'): 'shotgrid:reviewList:edit',
    ('PUT', '/shot-grid/review-lists/{reviewListId}/versions/order'): 'shotgrid:reviewList:edit',
    ('POST', '/shot-grid/review-lists/{reviewListId}/activate'): 'shotgrid:reviewList:activate',
    ('POST', '/shot-grid/review-lists/{reviewListId}/complete'): 'shotgrid:reviewList:complete',
    ('POST', '/shot-grid/review-lists/{reviewListId}/archive'): 'shotgrid:reviewList:archive',
    ('GET', '/shot-grid/versions/{versionId}/notes'): 'shotgrid:note:list',
    ('POST', '/shot-grid/versions/{versionId}/notes'): 'shotgrid:note:add',
    ('GET', '/shot-grid/notes/{noteId}/replies'): 'shotgrid:note:list',
    ('POST', '/shot-grid/notes/{noteId}/reply'): 'shotgrid:note:reply',
    ('POST', '/shot-grid/notes/{noteId}/resolve'): 'shotgrid:note:resolve',
    ('GET', '/shot-grid/versions/{versionId}/review-actions'): 'shotgrid:version:query',
    ('POST', '/shot-grid/versions/{versionId}/review-actions'): 'shotgrid:version:review',
}


def test_review_routes_match_review_contract_and_permissions() -> None:
    actual = {}
    for route in review_controller.routes:
        permissions = [
            dependency.dependency.perm
            for dependency in route.dependencies
            if isinstance(dependency.dependency, CheckUserInterfaceAuth)
        ]
        assert len(permissions) == 1
        for method in route.methods:
            actual[(method, route.path)] = permissions[0]

    assert review_controller.order_num == REVIEW_ROUTER_ORDER
    assert actual == EXPECTED_ROUTES


def test_review_action_openapi_documents_service_required_idempotency_header_and_lock_version() -> None:
    app = FastAPI()
    app.include_router(review_controller)
    operation = app.openapi()['paths']['/shot-grid/versions/{versionId}/review-actions']['post']

    idempotency = next(parameter for parameter in operation['parameters'] if parameter['name'] == 'X-Idempotency-Key')
    assert idempotency['required'] is False
    assert '业务必填' in idempotency['description']
    assert 'maxLength' not in idempotency['schema']
    request_schema = operation['requestBody']['content']['application/json']['schema']
    assert request_schema['$ref'].endswith('/ShotGridReviewActionCreateModel')
    action_schema = app.openapi()['components']['schemas']['ShotGridReviewActionCreateModel']
    assert {'actionType', 'lockVersion'} <= set(action_schema['required'])


def test_review_route_bigint_path_bounds_are_in_openapi() -> None:
    app = FastAPI()
    app.include_router(review_controller)
    operation = app.openapi()['paths']['/shot-grid/versions/{versionId}']['get']
    version_id = next(parameter for parameter in operation['parameters'] if parameter['name'] == 'versionId')

    assert version_id['schema']['exclusiveMinimum'] == 0
    assert version_id['schema']['maximum'] == SQL_BIGINT_MAX
