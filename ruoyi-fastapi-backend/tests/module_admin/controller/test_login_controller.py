import json

import pytest
from fastapi import FastAPI

from module_admin.controller.login_controller import get_login_user_info, login_controller
from module_admin.entity.vo.user_vo import CurrentUserInfoModel, CurrentUserModel

EXPECTED_SUCCESS_CODE = 200
EXPECTED_USER_ID = 2


def _current_user_with_ignored_password() -> CurrentUserModel:
    user = CurrentUserInfoModel.model_validate(
        {
            'userId': 2,
            'userName': 'creator',
            'nickName': '制作人员',
            'password': '$2b$12$should-never-leave-the-server',
        }
    )
    return CurrentUserModel(
        permissions=['shotgrid:navigation:list'],
        roles=['creator'],
        user=user,
    )


def test_get_info_openapi_uses_password_free_current_user_schema() -> None:
    app = FastAPI()
    app.include_router(login_controller)

    schemas = app.openapi()['components']['schemas']
    current_user_schema = schemas['DynamicResponseModel_CurrentUserModel_']
    user_schema_ref = current_user_schema['properties']['user']['anyOf'][0]['$ref']

    assert user_schema_ref == '#/components/schemas/CurrentUserInfoModel'
    assert 'password' not in schemas['CurrentUserInfoModel']['properties']


@pytest.mark.asyncio
async def test_get_info_controller_never_serializes_ignored_password() -> None:
    response = await get_login_user_info(object(), _current_user_with_ignored_password())
    payload = json.loads(response.body)

    assert payload['code'] == EXPECTED_SUCCESS_CODE
    assert payload['user']['userId'] == EXPECTED_USER_ID
    assert payload['user']['userName'] == 'creator'
    assert 'password' not in payload['user']
