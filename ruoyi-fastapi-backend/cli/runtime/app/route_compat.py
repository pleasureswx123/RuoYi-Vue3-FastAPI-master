from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from fastapi.routing import APIRoute

try:
    from fastapi.routing import iter_route_contexts as _fastapi_iter_route_contexts
except ImportError:
    _fastapi_iter_route_contexts = None


@dataclass(frozen=True)
class AppRouteContext:
    """兼容旧版 FastAPI 的应用路由上下文。"""

    original_route: APIRoute
    path: str
    methods: set[str]
    name: str
    summary: str | None
    operation_id: str | None
    tags: list[str]
    include_in_schema: bool


def _join_route_path(prefix: str, path: str) -> str:
    """拼接挂载路径与子路由路径。"""

    if not prefix:
        return path
    if not path:
        return prefix
    return f'{prefix.rstrip("/")}/{path.lstrip("/")}'


def _iter_legacy_route_contexts(routes: Iterable[Any], *, prefix: str = '') -> Iterator[AppRouteContext]:
    """在不支持 ``iter_route_contexts`` 的 FastAPI 中递归展开路由。"""

    for route in routes:
        route_path = _join_route_path(prefix, str(getattr(route, 'path', '') or ''))
        if isinstance(route, APIRoute):
            yield AppRouteContext(
                original_route=route,
                path=route_path,
                methods=set(route.methods or set()),
                name=route.name,
                summary=route.summary,
                operation_id=route.operation_id,
                tags=list(route.tags or []),
                include_in_schema=route.include_in_schema,
            )
            continue

        nested_routes = getattr(route, 'routes', None)
        if nested_routes:
            yield from _iter_legacy_route_contexts(nested_routes, prefix=route_path)


def iter_app_route_contexts(routes: Iterable[Any]) -> Iterator[Any]:
    """使用当前 FastAPI 的路由上下文能力，并兼容缺少该 API 的版本。"""

    if _fastapi_iter_route_contexts is not None:
        yield from _fastapi_iter_route_contexts(routes)
        return

    yield from _iter_legacy_route_contexts(routes)
