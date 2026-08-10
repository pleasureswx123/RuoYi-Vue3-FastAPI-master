import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
CONTROLLER_PATH = BACKEND_ROOT / 'module_shot_grid' / 'controller' / 'asset_import_controller.py'
ASSET_IMPORT_ROUTE_COUNT = 2


def test_asset_import_controller_has_no_generic_log_decorator() -> None:
    """通用 Log 会吞领域异常状态，正式提交由 Service 在同一事务写审计。"""
    tree = ast.parse(CONTROLLER_PATH.read_text(encoding='utf-8'))
    functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]

    assert not any(
        isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name) and decorator.func.id == 'Log'
        for function in functions
        for decorator in function.decorator_list
    )


def test_asset_import_controller_uses_project_role_and_interface_permissions() -> None:
    source = CONTROLLER_PATH.read_text(encoding='utf-8')

    assert source.count("UserInterfaceAuthDependency('shotgrid:asset:import')") == ASSET_IMPORT_ROUTE_COUNT
    assert source.count("ProjectRoleDependency('director')") == ASSET_IMPORT_ROUTE_COUNT
    assert "Header(alias='X-Idempotency-Key'" in source
