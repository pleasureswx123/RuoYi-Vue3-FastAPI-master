# ruff: noqa: ANN201
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_shot_grid_download_keeps_range_business_name_and_header_safety_contract():
    source = (ROOT / 'module_shot_grid/controller/version_controller.py').read_text(encoding='utf-8')
    assert "request.headers.get('Range')" in source
    assert 'UploadUtil.build_download_headers(relation.business_file_name' in source
    assert 'status_code=206 if result.byte_range.is_partial else 200' in source
    upload = (ROOT / 'utils/upload_util.py').read_text(encoding='utf-8')
    assert 'safe_name = cls.get_original_filename(filename)' in upload
    assert "'Accept-Ranges': 'bytes'" in upload
    assert "headers['Content-Range']" in upload
