"""生成唯一、可追踪且符合 Shot Grid camelCase 契约的测试数据。"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from shot_grid.config import ShotGridSettings


@dataclass(frozen=True)
class ShotGridDataFactory:
    run_id: str

    @classmethod
    def create(cls) -> 'ShotGridDataFactory':
        stamp = datetime.now(UTC).strftime('%m%d%H%M%S')
        return cls(f'E{stamp}{secrets.token_hex(2).upper()}')

    def project(self, settings: ShotGridSettings) -> dict:
        code = self.run_id[-12:]
        return {
            'projectCode': code,
            'projectName': f'E2E验收-{self.run_id}',
            'projectType': 'ai_short_film',
            'aspectRatio': '16:9',
            'storageRootId': settings.nas_root_id,
            'projectDirectoryName': self.run_id,
            'directorUserIds': [settings.director.user_id],
            'members': [{'userId': settings.producer.user_id, 'projectRole': 'producer', 'producerCode': 'E2E'}],
            'remark': f'自动化验收 {self.run_id}',
        }

    @staticmethod
    def episode() -> dict:
        return {'episodeNo': 1, 'episodeName': '第一集', 'sortOrder': 1}

    @staticmethod
    def scene(episode_id: int) -> dict:
        return {'episodeId': episode_id, 'sceneNo': 1, 'sceneName': '开场', 'sortOrder': 1}

    @staticmethod
    def shot(episode_id: int, scene_id: int) -> dict:
        return {
            'episodeId': episode_id,
            'sceneId': scene_id,
            'shotNo': 1,
            'durationMs': 1000,
            'description': '验收镜头',
        }

    def asset(self, asset_type: str) -> dict:
        return {'assetName': f'{asset_type}-{self.run_id}', 'assetType': asset_type, 'sortOrder': 1}

    @staticmethod
    def asset_item(asset_id: int, name: str) -> dict:
        return {'assetId': asset_id, 'productionItem': name, 'sortOrder': 1}
