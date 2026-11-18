import os


class Config:
    frontend_url = os.environ.get('TEST_FRONTEND_URL', 'http://localhost:18080').rstrip('/')
    backend_url = os.environ.get('TEST_BACKEND_URL', 'http://localhost:19099').rstrip('/')
