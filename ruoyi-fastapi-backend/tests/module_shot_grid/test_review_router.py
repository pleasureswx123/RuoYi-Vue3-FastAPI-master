import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from common.aspect.interface_auth import CheckUserInterfaceAuth
from module_shot_grid.controller.review_controller import review_controller
from module_shot_grid.entity.vo.review_vo import ShotGridReviewActionCreateModel

REVIEW_ROUTER_ORDER = 47
SQL_BIGINT_MAX = 9_223_372_036_854_775_807

EXPECTED_ROUTES = {
    ('GET', '/shot-grid/review-lists/mine'): 'shotgrid:reviewList:list',
    ('GET', '/shot-grid/review-lists/mine/projects'): 'shotgrid:reviewList:list',
    ('GET', '/shot-grid/review-lists/mine/producers'): 'shotgrid:reviewList:list',
    ('GET', '/shot-grid/versions/mine/recent'): 'shotgrid:version:list',
    ('GET', '/shot-grid/versions/mine/projects'): 'shotgrid:version:list',
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
    ('GET', '/shot-grid/tasks/{taskId}/issues'): 'shotgrid:note:list',
    ('GET', '/shot-grid/versions/{versionId}/review-context'): 'shotgrid:version:review',
    ('PUT', '/shot-grid/versions/{versionId}/selected-candidate'): 'shotgrid:version:review',
    ('POST', '/shot-grid/versions/{versionId}/issues'): 'shotgrid:note:add',
    ('POST', '/shot-grid/versions/{versionId}/additional-issues'): 'shotgrid:note:add',
    ('PUT', '/shot-grid/versions/{versionId}/issue-drafts/{draftId}'): 'shotgrid:note:add',
    ('DELETE', '/shot-grid/versions/{versionId}/issue-drafts/{draftId}'): 'shotgrid:note:add',
    ('GET', '/shot-grid/issue-drafts/{draftId}/reference-files/{fileId}/download'): 'shotgrid:file:download',
    ('GET', '/shot-grid/issues/{issueId}/reference-files/{fileId}/download'): 'shotgrid:file:download',
    ('GET', '/shot-grid/versions/{versionId}/review-actions'): 'shotgrid:version:query',
    ('POST', '/shot-grid/versions/{versionId}/review-actions'): 'shotgrid:version:review',
    ('POST', '/shot-grid/versions/{versionId}/final-delivery/retry'): 'shotgrid:version:retry',
    ('POST', '/shot-grid/projects/{projectId}/review-overall-feedback/batch-reject'): [
        'shotgrid:note:add',
        'shotgrid:version:review',
    ],
    ('POST', '/shot-grid/projects/{projectId}/review-overall-feedback/batch'): [
        'shotgrid:note:add',
        'shotgrid:version:review',
    ],
    ('PUT', '/shot-grid/versions/{versionId}/additional-issues/{issueId}'): 'shotgrid:note:add',
    ('DELETE', '/shot-grid/versions/{versionId}/additional-issues/{issueId}'): 'shotgrid:note:add',
    ('PUT', '/shot-grid/versions/{versionId}/candidates/{candidateId}/generation-prompt'): 'shotgrid:version:add',
    ('POST', '/shot-grid/versions/{versionId}/transfer-revision'): 'shotgrid:task:assign',
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
        if route.path.endswith(('/review-overall-feedback/batch', '/review-overall-feedback/batch-reject')):
            assert all(
                dependency.dependency.is_strict
                for dependency in route.dependencies
                if isinstance(dependency.dependency, CheckUserInterfaceAuth)
            )
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
    assert 'selectedCandidateId' not in action_schema['required']
    assert ShotGridReviewActionCreateModel(actionType='reject', lockVersion=0).selected_candidate_id is None
    with pytest.raises(ValidationError, match='审核通过时必须选择最终交付文件'):
        ShotGridReviewActionCreateModel(actionType='approve', lockVersion=0)


def test_candidate_selection_openapi_documents_required_payload_and_idempotency_header() -> None:
    app = FastAPI()
    app.include_router(review_controller)
    operation = app.openapi()['paths']['/shot-grid/versions/{versionId}/selected-candidate']['put']

    idempotency = next(parameter for parameter in operation['parameters'] if parameter['name'] == 'X-Idempotency-Key')
    assert idempotency['required'] is False
    assert '业务必填' in idempotency['description']
    request_schema = operation['requestBody']['content']['application/json']['schema']
    assert request_schema['$ref'].endswith('/ShotGridVersionCandidateSelectModel')
    command_schema = app.openapi()['components']['schemas']['ShotGridVersionCandidateSelectModel']
    assert {'candidateId', 'lockVersion'} <= set(command_schema['required'])


def test_review_route_bigint_path_bounds_are_in_openapi() -> None:
    app = FastAPI()
    app.include_router(review_controller)
    operation = app.openapi()['paths']['/shot-grid/versions/{versionId}']['get']
    version_id = next(parameter for parameter in operation['parameters'] if parameter['name'] == 'versionId')

    assert version_id['schema']['exclusiveMinimum'] == 0
    assert version_id['schema']['maximum'] == SQL_BIGINT_MAX
