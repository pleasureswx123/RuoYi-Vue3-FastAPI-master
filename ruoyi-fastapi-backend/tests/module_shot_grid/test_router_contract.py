from pathlib import Path

from fastapi import FastAPI

from common.router import RouterRegister


def test_shot_grid_navigation_controller_is_auto_discoverable() -> None:
    router_register = RouterRegister(app=FastAPI())

    controller_files = router_register._find_controller_files()

    assert any(
        Path(path).parts[-3:] == ('module_shot_grid', 'controller', 'navigation_controller.py')
        for path in controller_files
    )
