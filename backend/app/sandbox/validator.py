from __future__ import annotations

import ast

from app.errors import AppError

ALLOWED_IMPORTS = {
    "pandas",
    "numpy",
    "sklearn",
    "matplotlib",
    "json",
    "math",
    "statistics",
}

FORBIDDEN_NAMES = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "open",
    "globals",
    "locals",
    "vars",
    "getattr",
    "setattr",
    "delattr",
    "input",
    "breakpoint",
}

FORBIDDEN_MODULES = {
    "os",
    "sys",
    "subprocess",
    "socket",
    "requests",
    "urllib",
    "shutil",
    "pathlib",
    "importlib",
    "ctypes",
    "pickle",
    "multiprocessing",
    "threading",
    "http",
    "ftplib",
    "paramiko",
}

MAX_CODE_LENGTH = 8000


def _fail(reason: str) -> None:
    raise AppError("SANDBOX_VALIDATION_ERROR", f"代码未通过安全检查：{reason}", 400)


def validate_code(code: str) -> None:
    """AST 白名单是第一层；Docker 隔离仍必须同时启用。"""
    if not code.strip():
        _fail("代码为空")
    if len(code) > MAX_CODE_LENGTH:
        _fail("代码超过长度上限")

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        _fail(f"语法错误: {exc.msg}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in ALLOWED_IMPORTS:
                    _fail(f"禁止导入 {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if node.level != 0 or root not in ALLOWED_IMPORTS:
                _fail(f"禁止导入 {node.module}")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES:
                _fail(f"禁止使用 {node.id}")
            if node.id in FORBIDDEN_MODULES:
                _fail(f"禁止访问模块 {node.id}")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                _fail("禁止访问双下划线属性")
            if node.attr in {"system", "popen", "remove", "unlink", "rmdir"}:
                _fail(f"禁止调用 {node.attr}")
        elif isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Name) and target.id in FORBIDDEN_NAMES:
                _fail(f"禁止调用 {target.id}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if value.startswith("/") or ".." in value or "${" in value:
                _fail("禁止绝对路径、上级目录或环境变量路径")
