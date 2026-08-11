from middlewares.transport_crypto_middleware import TransportCryptoMiddleware


def test_only_exact_shot_template_get_bypasses_json_envelope() -> None:
    path = '/shot-grid/imports/shots/template'

    assert TransportCryptoMiddleware._is_shot_grid_template_download('GET', path) is True
    assert TransportCryptoMiddleware._is_shot_grid_template_download('POST', path) is False
    assert TransportCryptoMiddleware._is_shot_grid_template_download('GET', f'{path}/metadata') is False
    assert TransportCryptoMiddleware._is_excluded_path(path) is False
    assert TransportCryptoMiddleware._is_excluded_path('/shot-grid/projects/1/shots') is False


def test_only_exact_authenticated_version_file_get_bypasses_json_envelope() -> None:
    download_path = '/shot-grid/versions/91/files/5ed39e04-2f29-45ab-a58c-4f8168f5131a/download'

    assert TransportCryptoMiddleware._is_shot_grid_version_file_download('GET', download_path) is True
    assert TransportCryptoMiddleware._is_shot_grid_version_file_download('POST', download_path) is False
    assert (
        TransportCryptoMiddleware._is_shot_grid_version_file_download(
            'GET',
            '/shot-grid/versions/0/files/5ed39e04-2f29-45ab-a58c-4f8168f5131a/download',
        )
        is False
    )
    assert (
        TransportCryptoMiddleware._is_shot_grid_version_file_download(
            'GET',
            '/shot-grid/versions/91/files/not-a-uuid/download',
        )
        is False
    )


def test_version_review_json_routes_remain_inside_required_crypto_policy() -> None:
    json_routes = (
        ('GET', '/shot-grid/versions/91'),
        ('GET', '/shot-grid/versions/91/notes'),
        ('POST', '/shot-grid/versions/91/review-actions'),
    )
    for method, path in json_routes:
        assert TransportCryptoMiddleware._is_excluded_path(path) is False
        assert TransportCryptoMiddleware._is_shot_grid_version_file_download(method, path) is False
