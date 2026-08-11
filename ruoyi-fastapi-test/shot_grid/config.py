"""Shot Grid 验收环境配置；所有敏感值只从环境变量读取。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Account:
    username: str
    password: str
    user_id: int


@dataclass(frozen=True)
class ShotGridSettings:
    frontend_url: str
    backend_url: str
    nas_root_id: int
    nas_mount_path: Path
    admin: Account
    director: Account
    producer: Account
    outsider: Account
    shot_video: Path
    asset_image: Path
    shot_excel: Path
    asset_excel: Path

    @classmethod
    def from_env(cls) -> 'ShotGridSettings':
        accounts = json.loads(os.environ['SHOT_GRID_E2E_ACCOUNTS'])

        def account(role: str) -> Account:
            value = accounts[role]
            return Account(value['username'], value['password'], int(value['userId']))

        samples = Path(os.environ['SHOT_GRID_E2E_SAMPLE_DIR']).resolve()
        return cls(
            frontend_url=os.getenv('SHOT_GRID_FRONTEND_URL', 'http://localhost:4173').rstrip('/'),
            backend_url=os.getenv('SHOT_GRID_BACKEND_URL', 'http://localhost:9099').rstrip('/'),
            nas_root_id=int(os.environ['SHOT_GRID_E2E_NAS_ROOT_ID']),
            nas_mount_path=Path(os.environ['SHOT_GRID_E2E_NAS_MOUNT_PATH']).resolve(),
            admin=account('admin'),
            director=account('director'),
            producer=account('producer'),
            outsider=account('outsider'),
            shot_video=samples / 'shot-v001.mp4',
            asset_image=samples / 'asset-v001.png',
            shot_excel=samples / 'shots.xlsx',
            asset_excel=samples / 'assets.xlsx',
        )

    def validate(self) -> None:
        accounts = (self.admin, self.director, self.producer, self.outsider)
        if len({item.username for item in accounts}) != 4 or len({item.user_id for item in accounts}) != 4:
            raise ValueError('四类验收账号的 username 和 userId 必须互不相同')
        if not self.nas_mount_path.is_dir():
            raise ValueError(f'真实 NAS 挂载目录不可访问：{self.nas_mount_path}')
        for sample in (self.shot_video, self.asset_image, self.shot_excel, self.asset_excel):
            if not sample.is_file():
                raise ValueError(f'缺少受控验收样本：{sample}')
