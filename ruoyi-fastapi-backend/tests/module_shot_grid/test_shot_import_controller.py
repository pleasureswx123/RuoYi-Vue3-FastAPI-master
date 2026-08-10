import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
CONTROLLER_PATH = BACKEND_ROOT / 'module_shot_grid' / 'controller' / 'shot_import_controller.py'


def test_import_controller_does_not_use_generic_log_decorator() -> None:
    """通用 Log 会吞掉领域异常状态码，导入接口改由 Service 同事务审计。"""
    tree = ast.parse(CONTROLLER_PATH.read_text(encoding='utf-8'))
    decorated_functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]

    assert not any(
        isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name) and decorator.func.id == 'Log'
        for function in decorated_functions
        for decorator in function.decorator_list
    )
