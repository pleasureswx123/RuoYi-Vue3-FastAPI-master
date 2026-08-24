from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.env import AppConfig


def add_cors_middleware(app: FastAPI) -> None:
    """
    添加跨域中间件

    :param app: FastAPI对象
    :return:
    """
    # 前端页面url
    origins = [origin.strip() for origin in AppConfig.app_cors_allowed_origins.split(',') if origin.strip()]
    if not origins or '*' in origins:
        origins = ['*']

    expose_headers = [
        'x-body-encrypted',
        'x-key-id',
        'x-encrypt-alg',
        'download-filename',
        'content-disposition',
        'accept-ranges',
        'content-range',
        'content-length',
    ]

    # 后台api允许跨域
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
        expose_headers=expose_headers,
    )
