"""统一实时失效通知：Redis 跨进程分发，业务数据仍由 HTTP 权限接口读取。"""

import asyncio
import json
import secrets
from uuid import uuid4

from fastapi import Request, WebSocket

from config.database import AsyncSessionLocal
from config.env import AppConfig
from module_admin.service.login_service import LoginService
from module_shot_grid.exceptions import shot_grid_error
from module_shot_grid.service.review_service import ShotGridReviewService

TOPIC = 'shot-grid.version'
TICKET_PREFIX = 'realtime:ticket:'
CHANNEL_PREFIX = 'realtime:v1:'
MAX_SUBSCRIPTIONS = 20
MAX_TICKETS_PER_MINUTE = 30
MAX_RESOURCE_ID = 9_007_199_254_740_991
MAX_MESSAGE_LENGTH = 4096
MAX_MESSAGES_PER_WINDOW = 100
AUTH_REFRESH_SECONDS = 20
HEARTBEAT_TIMEOUT_SECONDS = 65
MAX_TICKET_LENGTH = 100


async def issue_ticket(request: Request, user_id: int) -> dict[str, object]:
    redis = request.app.state.redis
    count = await redis.eval(
        "local n = redis.call('INCR', KEYS[1]); if n == 1 then redis.call('EXPIRE', KEYS[1], 60) end; return n",
        1,
        f'realtime:ticket-rate:{user_id}',
    )
    if count > MAX_TICKETS_PER_MINUTE:
        raise shot_grid_error(429, 'REALTIME_RATE_LIMIT', '实时连接过于频繁，请稍后重试')
    ticket = secrets.token_urlsafe(32)
    origin = request.headers.get('origin') or str(request.base_url).rstrip('/')
    await redis.set(
        f'{TICKET_PREFIX}{ticket}',
        json.dumps(
            {
                'token': request.headers.get('authorization', ''),
                'origin': origin,
            }
        ),
        ex=30,
    )
    return {'ticket': ticket, 'expiresIn': 30}


async def authorize(websocket: WebSocket, token: str, resource_ids: set[int]) -> None:
    """每次订阅、推送及心跳均重新检查登录、接口权限和项目数据范围。"""
    async with AsyncSessionLocal() as db:
        user = await LoginService.get_current_user(websocket, token, db)
        if not user.user or user.user.status != '0':
            raise ValueError('账号不可用')
        if not {'*:*:*', 'shotgrid:version:query'}.intersection(user.permissions):
            raise ValueError('无版本读取权限')
        for resource_id in resource_ids:
            await ShotGridReviewService._resolve_version_access(db, resource_id, user)


def validate_subscription(message: dict[str, object]) -> int:
    resource_id = message.get('resourceId')
    if message.get('topic') != TOPIC or type(resource_id) is not int or not 0 < resource_id <= MAX_RESOURCE_ID:
        raise ValueError('订阅参数无效')
    return resource_id


class RealtimeConnection:
    """每条连接的订阅和有界消息状态；共享通知保存在 Redis。"""

    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.redis = websocket.app.state.redis
        self.pubsub = None
        self.token = ''
        self.subscriptions: set[int] = set()
        self.receive_task = None
        self.event_task = None
        self.last_ping = 0.0

    async def authenticate(self, origin: str) -> None:
        raw = await asyncio.wait_for(self.websocket.receive_text(), timeout=10)
        message = self.parse_message(raw)
        ticket = message.get('ticket')
        if message.get('type') != 'auth' or not isinstance(ticket, str) or len(ticket) > MAX_TICKET_LENGTH:
            raise ValueError('认证参数无效')
        ticket_data = await self.redis.getdel(f'{TICKET_PREFIX}{ticket}')
        if not ticket_data:
            raise ValueError('票据失效')
        credentials = json.loads(ticket_data)
        if credentials['origin'] != origin:
            raise ValueError('票据来源不一致')
        self.token = credentials['token']
        await authorize(self.websocket, self.token, set())
        self.pubsub = self.redis.pubsub()
        # 保证 Redis 监听连接已初始化，连接专用频道不传输业务数据。
        await self.pubsub.subscribe(f'{CHANNEL_PREFIX}connection:{uuid4()}')
        await self.send({'type': 'ready', 'protocolVersion': 1})

    @staticmethod
    def parse_message(raw: str) -> dict:
        if len(raw) > MAX_MESSAGE_LENGTH:
            raise ValueError('消息过长')
        message = json.loads(raw)
        if not isinstance(message, dict):
            raise ValueError('消息无效')
        return message

    async def send(self, message: dict) -> None:
        await asyncio.wait_for(self.websocket.send_json(message), timeout=5)

    async def handle_message(self, raw: str) -> None:
        message = self.parse_message(raw)
        if message.get('type') == 'ping':
            self.last_ping = asyncio.get_running_loop().time()
            await self.send({'type': 'pong'})
            return
        if message.get('type') not in {'subscribe', 'unsubscribe'}:
            raise ValueError('不支持的消息')
        resource_id = validate_subscription(message)
        channel = f'{CHANNEL_PREFIX}{TOPIC}:{resource_id}'
        if message['type'] == 'unsubscribe':
            await self.pubsub.unsubscribe(channel)
            self.subscriptions.discard(resource_id)
            return
        if len(self.subscriptions | {resource_id}) > MAX_SUBSCRIPTIONS:
            raise ValueError('订阅过多')
        await authorize(self.websocket, self.token, {resource_id})
        await self.pubsub.subscribe(channel)
        self.subscriptions.add(resource_id)
        await self.send({'type': 'subscribed', 'topic': TOPIC, 'resourceId': resource_id})

    async def handle_event(self, item: dict | None) -> None:
        if not item:
            return
        event = json.loads(item['data'])
        resource_id = event.get('resourceId')
        if resource_id in self.subscriptions and event.get('topic') == TOPIC:
            await authorize(self.websocket, self.token, {resource_id})
            await self.send(event)

    async def listen(self) -> None:
        self.receive_task = asyncio.create_task(self.websocket.receive_text())
        self.event_task = asyncio.create_task(self.pubsub.get_message(ignore_subscribe_messages=True, timeout=1))
        loop = asyncio.get_running_loop()
        self.last_ping = loop.time()
        last_check = self.last_ping
        count = 0
        while True:
            done, _ = await asyncio.wait(
                {self.receive_task, self.event_task}, timeout=5, return_when=asyncio.FIRST_COMPLETED
            )
            now = loop.time()
            if now - self.last_ping > HEARTBEAT_TIMEOUT_SECONDS:
                raise ValueError('心跳超时')
            if now - last_check >= AUTH_REFRESH_SECONDS:
                await authorize(self.websocket, self.token, self.subscriptions)
                last_check = now
                count = 0
            if self.receive_task in done:
                count += 1
                if count > MAX_MESSAGES_PER_WINDOW:
                    raise ValueError('消息过于频繁')
                await self.handle_message(self.receive_task.result())
                self.receive_task = asyncio.create_task(self.websocket.receive_text())
            if self.event_task in done:
                await self.handle_event(self.event_task.result())
                self.event_task = asyncio.create_task(
                    self.pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
                )

    async def close(self) -> None:
        tasks = [task for task in (self.receive_task, self.event_task) if task]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self.pubsub:
            await self.pubsub.aclose()


async def run_connection(websocket: WebSocket) -> None:
    """单连接双向订阅/心跳协议；不接受业务写命令。"""
    origin = websocket.headers.get('origin')
    allowed = {value.strip() for value in AppConfig.app_cors_allowed_origins.split(',')}
    if not origin or ('*' not in allowed and origin not in allowed):
        await websocket.close(code=4403)
        return
    await websocket.accept()
    connection = RealtimeConnection(websocket)
    try:
        await connection.authenticate(origin)
        await connection.listen()
    except Exception:
        # 不回显令牌、Redis 载荷及鉴权异常详情。
        try:
            await websocket.close(code=4401)
        except RuntimeError:
            pass
    finally:
        await connection.close()
