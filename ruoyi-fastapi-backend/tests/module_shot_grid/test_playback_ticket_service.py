from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.config import ShotGridPlaybackConfig
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.playback_ticket_service import ShotGridPlaybackTicketService

VERSION_ID = 40
USER_ID = 60
FILE_ID = '5ed39e04-2f29-45ab-a58c-4f8168f5131a'
ACCESS_TOKEN = 'current-access-token'
SESSION_ID = 'session-1'


def playback_config() -> ShotGridPlaybackConfig:
    return ShotGridPlaybackConfig(ticketTtlSeconds=600, redisKeyPrefix='test:playback')


def current_user() -> CurrentUserModel:
    return CurrentUserModel(
        permissions=['shotgrid:file:download'],
        roles=[],
        user=UserInfoModel(userId=USER_ID, userName='reviewer'),
    )


@pytest.mark.asyncio
async def test_ticket_is_stored_by_hash_and_bound_to_session_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = AsyncMock()
    redis.set.return_value = True
    request = SimpleNamespace(headers={'Authorization': f'Bearer {ACCESS_TOKEN}'})
    monkeypatch.setattr(
        'module_shot_grid.service.playback_ticket_service.JwtUtil.decode',
        MagicMock(return_value={'session_id': SESSION_ID}),
    )
    monkeypatch.setattr(ShotGridPlaybackTicketService, 'new_token', lambda: 'ticket-1')

    token = await ShotGridPlaybackTicketService.create(
        redis,
        request,
        version_id=VERSION_ID,
        file_id=FILE_ID,
        current_user=current_user(),
        config=playback_config(),
    )

    assert token == 'ticket-1'
    redis.set.assert_awaited_once()
    key, payload = redis.set.await_args.args
    assert key != 'ticket-1'
    assert ACCESS_TOKEN not in payload
    assert SESSION_ID in payload
    assert redis.set.await_args.kwargs == {'ex': 600, 'nx': True}


@pytest.mark.asyncio
async def test_ticket_rejects_different_resource_and_invalidated_session() -> None:
    config = playback_config()
    token = 'ticket-1'
    payload = (
        '{"versionId":40,"fileId":"5ed39e04-2f29-45ab-a58c-4f8168f5131a",'
        '"userId":60,"sessionId":"session-1","accessTokenHash":"'
        f'{ShotGridPlaybackTicketService.token_hash(ACCESS_TOKEN)}"}}'
    )
    redis = AsyncMock()
    redis.get.side_effect = [payload, payload, None]

    with pytest.raises(ShotGridDomainException, match='目标文件不匹配'):
        await ShotGridPlaybackTicketService.get(
            redis,
            token,
            version_id=VERSION_ID + 1,
            file_id=FILE_ID,
            config=config,
        )

    with pytest.raises(ShotGridDomainException, match='登录会话已失效'):
        await ShotGridPlaybackTicketService.get(
            redis,
            token,
            version_id=VERSION_ID,
            file_id=FILE_ID,
            config=config,
        )
