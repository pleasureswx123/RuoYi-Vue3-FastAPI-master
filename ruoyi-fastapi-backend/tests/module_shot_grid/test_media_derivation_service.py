from pathlib import Path

import pytest
from PIL import Image

from module_shot_grid.config import ShotGridMediaWorkerConfig
from module_shot_grid.service.media_derivation_service import (
    MediaDerivationError,
    ShotGridMediaDerivationService,
)

THUMBNAIL_EDGE = 128
PROXY_EDGE = 480


def media_config() -> ShotGridMediaWorkerConfig:
    return ShotGridMediaWorkerConfig(
        enabled=True,
        max_attempts=2,
        retry_delays_seconds=(1,),
        thumbnail_max_edge=THUMBNAIL_EDGE,
        image_proxy_max_edge=PROXY_EDGE,
    )


def test_media_derivation_uses_official_version_reference_type() -> None:
    assert ShotGridMediaDerivationService.VERSION_REFERENCE_TYPE == 'shotgrid_version'


def test_image_derivation_generates_distinct_thumbnail_and_proxy(tmp_path: Path) -> None:
    source = tmp_path / 'source.png'
    Image.new('RGB', (1200, 600), color=(18, 52, 86)).save(source)
    target = tmp_path / 'derived'
    target.mkdir()

    outputs = ShotGridMediaDerivationService._derive_image(
        source,
        target,
        Path('derived/2026/08/40'),
        media_config(),
    )

    assert [item.role for item in outputs] == ['thumbnail', 'proxy_media']
    with Image.open(outputs[0].path) as thumbnail:
        assert max(thumbnail.size) <= THUMBNAIL_EDGE
    with Image.open(outputs[1].path) as proxy:
        assert max(proxy.size) <= PROXY_EDGE
    assert outputs[0].path != source
    assert outputs[1].path != source


@pytest.mark.asyncio
async def test_video_derivation_fails_explicitly_without_ffmpeg(tmp_path: Path) -> None:
    config = media_config().model_copy(update={'ffmpeg_path': str(tmp_path / 'missing-ffmpeg.exe')})
    with pytest.raises(MediaDerivationError, match='FFmpeg'):
        await ShotGridMediaDerivationService._derive_video(
            tmp_path / 'source.mp4',
            tmp_path,
            Path('derived/2026/08/40'),
            config,
        )
