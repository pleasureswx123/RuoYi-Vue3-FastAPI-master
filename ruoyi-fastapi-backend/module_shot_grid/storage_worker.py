"""Shot Grid NAS 目录操作的独立进程入口。"""

import argparse
import asyncio


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='运行 Shot Grid NAS 目录操作 Worker')
    parser.add_argument('--worker-id', required=True, help='本次进程唯一且不含凭据的 Worker 标识')
    parser.add_argument('--idle-seconds', type=float, default=1.0, help='队列空闲轮询间隔秒数')
    return parser


async def run(worker_id: str, idle_seconds: float) -> None:
    if idle_seconds <= 0:
        raise ValueError('idle-seconds 必须大于 0')

    # 帮助和参数错误不应初始化数据库；实际启动循环时才加载运行依赖。
    from config.database import AsyncSessionLocal  # noqa: PLC0415
    from module_shot_grid.service.storage_operation_worker import (  # noqa: PLC0415
        ShotGridStorageOperationWorker,
    )

    worker = ShotGridStorageOperationWorker(AsyncSessionLocal, worker_id)
    await worker.run_forever(idle_seconds=idle_seconds)


def main() -> None:
    args = build_parser().parse_args()
    try:
        asyncio.run(run(args.worker_id, args.idle_seconds))
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
