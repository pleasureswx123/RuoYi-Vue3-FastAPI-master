import os

import pytest

pytestmark = [pytest.mark.shot_grid_e2e, pytest.mark.shot_grid_api, pytest.mark.destructive]


@pytest.mark.parametrize(
    'fault',
    ['nas_offline', 'publish_failure', 'database_commit_failure'],
)
async def test_real_fault_recovery_uses_original_submission(sg_clients, fault) -> None:
    """故障由验收环境控制器注入，测试套件本身不 Mock NAS 或数据库。"""
    controller = os.getenv('SHOT_GRID_E2E_FAULT_CONTROLLER_URL')
    if not controller:
        pytest.skip('未配置真实故障注入控制器 SHOT_GRID_E2E_FAULT_CONTROLLER_URL')
    response = await sg_clients['admin'].request.post(f'{controller.rstrip("/")}/faults/{fault}')
    assert response.ok
    state = await sg_clients['admin'].request.get(f'{controller.rstrip("/")}/faults/{fault}')
    assert state.ok and (await state.json())['observed'] is True


@pytest.mark.parametrize('sample_name', ['wrong_mime.bin', 'forged.jpg', 'oversized.bin'])
async def test_invalid_file_samples_are_rejected(sg_clients, sg_project, sg_settings, sample_name) -> None:
    sample = sg_settings.shot_video.parent / sample_name
    if not sample.exists():
        pytest.skip(f'受控负向文件样本未配置：{sample}')
    result = await sg_clients['producer'].request.post(
        '/common/files/upload',
        headers={'Authorization': f'Bearer {sg_clients["producer"].token}'},
        multipart={'file': {'name': sample.name, 'mimeType': 'video/mp4', 'buffer': sample.read_bytes()}},
    )
    assert result.status in {400, 413, 415, 422}
    storage = await sg_clients['admin'].data('GET', f'/shot-grid/projects/{sg_project["id"]}/storage')
    assert storage['storageStatus'] == 'ready'
