"""统一实时通道的鉴权、隔离和一次性票据协议验证。"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from module_realtime.service import realtime_publisher as publisher
from module_realtime.service import realtime_service as realtime


def connection() -> tuple[realtime.RealtimeConnection, SimpleNamespace, SimpleNamespace]:
    redis = SimpleNamespace(
        getdel=AsyncMock(),
        pubsub=lambda: SimpleNamespace(subscribe=AsyncMock(), unsubscribe=AsyncMock(), aclose=AsyncMock()),
    )
    ws = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(redis=redis)), send_json=AsyncMock(), receive_text=AsyncMock()
    )
    return realtime.RealtimeConnection(ws), ws, redis


@pytest.mark.asyncio
async def test_ticket_is_single_use_and_origin_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    c, ws, redis = connection()
    ws.receive_text.return_value = json.dumps({'type': 'auth', 'ticket': 'opaque'})
    redis.getdel.side_effect = [json.dumps({'token': 'secret', 'origin': 'http://local'}), None]
    auth = AsyncMock()
    monkeypatch.setattr(realtime, 'authorize', auth)
    await c.authenticate('http://local')
    auth.assert_awaited_once_with(ws, 'secret', set())
    with pytest.raises(ValueError, match='票据失效'):
        await c.authenticate('http://local')
    redis.getdel.side_effect = None
    redis.getdel.return_value = json.dumps({'token': 'secret', 'origin': 'http://local'})
    with pytest.raises(ValueError, match='来源'):
        await c.authenticate('http://other')


@pytest.mark.asyncio
async def test_subscribe_and_events_recheck_access_and_unsubscribe(monkeypatch: pytest.MonkeyPatch) -> None:
    c, ws, redis = connection()
    c.pubsub = redis.pubsub()
    c.token = 'secret'
    auth = AsyncMock()
    monkeypatch.setattr(realtime, 'authorize', auth)
    command = {'type': 'subscribe', 'topic': realtime.TOPIC, 'resourceId': 29}
    await c.handle_message(json.dumps(command))
    assert c.subscriptions == {29}
    auth.assert_awaited_with(ws, 'secret', {29})
    ws.send_json.reset_mock()
    await c.handle_event({'data': json.dumps({'topic': realtime.TOPIC, 'resourceId': 30})})
    ws.send_json.assert_not_awaited()
    auth.side_effect = ValueError('已撤销权限')
    with pytest.raises(ValueError):
        await c.handle_event({'data': json.dumps({'topic': realtime.TOPIC, 'resourceId': 29})})
    ws.send_json.assert_not_awaited()
    auth.side_effect = None
    await c.handle_message(json.dumps({**command, 'type': 'unsubscribe'}))
    assert c.subscriptions == set()
    await c.handle_message(json.dumps({'type': 'ping'}))
    ws.send_json.assert_awaited_with({'type': 'pong'})


@pytest.mark.parametrize(
    'message',
    [
        {'topic': 'other', 'resourceId': 1},
        {'topic': realtime.TOPIC, 'resourceId': True},
        {'topic': realtime.TOPIC, 'resourceId': -1},
        {'topic': realtime.TOPIC, 'resourceId': '1'},
    ],
)
def test_invalid_subscriptions(message: dict) -> None:
    with pytest.raises(ValueError):
        realtime.validate_subscription(message)


@pytest.mark.asyncio
async def test_authorize_checks_session_permission_and_project(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    factory = AsyncMock()
    factory.__aenter__.return_value = db
    monkeypatch.setattr(realtime, 'AsyncSessionLocal', lambda: factory)
    user = SimpleNamespace(user=SimpleNamespace(status='0'), permissions=['shotgrid:version:query'])
    login = AsyncMock(return_value=user)
    scope = AsyncMock()
    monkeypatch.setattr(realtime.LoginService, 'get_current_user', login)
    monkeypatch.setattr(realtime.ShotGridReviewService, '_resolve_version_access', scope)
    await realtime.authorize(None, 'secret', {29})
    scope.assert_awaited_once_with(db, 29, user)
    user.permissions = []
    with pytest.raises(ValueError):
        await realtime.authorize(None, 'secret', {29})
    user.permissions = ['*:*:*']
    user.user.status = '1'
    with pytest.raises(ValueError):
        await realtime.authorize(None, 'secret', {29})
    user.user.status = '0'
    login.side_effect = ValueError('会话撤销')
    with pytest.raises(ValueError):
        await realtime.authorize(None, 'secret', {29})


@pytest.mark.asyncio
async def test_publisher_failure_does_not_reverse_business_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(publisher, '_publish', AsyncMock(side_effect=RedisConnectionError()))
    await publisher.publish_version_changed(29, 'candidates.appended')


@pytest.mark.asyncio
async def test_ticket_ttl_no_token_in_response_and_rate_limit() -> None:
    redis = SimpleNamespace(eval=AsyncMock(return_value=1), set=AsyncMock())
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(redis=redis)),
        headers={'origin': 'http://local', 'authorization': 'Bearer secret'},
    )
    result = await realtime.issue_ticket(request, 7)
    assert set(result) == {'ticket', 'expiresIn'}
    expected_ttl = 30
    assert result['expiresIn'] == expected_ttl
    assert 'secret' not in str(result)
    assert redis.set.await_args.kwargs['ex'] == expected_ttl
    redis.eval.return_value = 31
    with pytest.raises(Exception, match='频繁'):
        await realtime.issue_ticket(request, 7)
