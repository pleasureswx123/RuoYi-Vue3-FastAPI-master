"""两个独立 ASGI 应用通过真实 Redis 收到同一通知；不使用业务数据。"""

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from config.get_redis import RedisUtil
from module_realtime.service import realtime_service as service
from module_realtime.service.realtime_publisher import publish_version_changed

pytestmark = pytest.mark.skipif(os.getenv('SHOT_GRID_RUN_REDIS_TESTS') != '1', reason='需显式启用真实 Redis 验证')
RESOURCE_ID = 8_888_888_801


def build_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.redis = await RedisUtil.create_redis_pool(log_enabled=False)
        yield
        await app.state.redis.aclose()

    app = FastAPI(lifespan=lifespan)

    @app.post('/ticket')
    async def ticket() -> dict[str, str]:

        value = uuid4().hex
        await app.state.redis.set(
            f'{service.TICKET_PREFIX}{value}',
            json.dumps(
                {
                    'token': 'isolated-test-session',
                    'origin': 'http://testserver',
                }
            ),
            ex=30,
        )
        return {'ticket': value}

    @app.post('/publish')
    async def publish() -> dict[str, bool]:
        await publish_version_changed(RESOURCE_ID, 'candidates.appended')
        return {'ok': True}

    @app.websocket('/ws')
    async def websocket(ws: WebSocket) -> None:
        await service.run_connection(ws)

    return app


def test_two_workers_receive_and_ticket_replay_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    async def authorize(ws: WebSocket, token: str, ids: set[int]) -> None:
        assert token == 'isolated-test-session'
        assert ids <= {RESOURCE_ID}

    monkeypatch.setattr(service, 'authorize', authorize)
    monkeypatch.setattr(service.AppConfig, 'app_cors_allowed_origins', 'http://testserver')
    with TestClient(build_app()) as first, TestClient(build_app()) as second:
        ticket1 = first.post('/ticket').json()['ticket']
        ticket2 = second.post('/ticket').json()['ticket']
        with (
            first.websocket_connect('/ws', headers={'origin': 'http://testserver'}) as one,
            second.websocket_connect('/ws', headers={'origin': 'http://testserver'}) as two,
        ):
            for socket, ticket in [(one, ticket1), (two, ticket2)]:
                socket.send_json({'type': 'auth', 'ticket': ticket})
                assert socket.receive_json()['type'] == 'ready'
                socket.send_json({'type': 'subscribe', 'topic': service.TOPIC, 'resourceId': RESOURCE_ID})
                assert socket.receive_json()['type'] == 'subscribed'
            first.post('/publish').raise_for_status()
            a = one.receive_json()
            b = two.receive_json()
            assert a == b
            assert a['reason'] == 'candidates.appended'
            assert set(a) == {'type', 'eventId', 'topic', 'resourceId', 'event', 'reason'}
            one.send_json({'type': 'ping'})
            assert one.receive_json() == {'type': 'pong'}
        with first.websocket_connect('/ws', headers={'origin': 'http://testserver'}) as replay:
            replay.send_json({'type': 'auth', 'ticket': ticket1})
            with pytest.raises(WebSocketDisconnect):
                replay.receive_json()
