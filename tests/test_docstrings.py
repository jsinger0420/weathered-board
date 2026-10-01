"""Every module, class and function in the project has a docstring.

Keeps the code documented as it grows: a new function without a
docstring fails this test, with its file and line in the message.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = sorted(p for folder in ("weathered_board", "tests") for p in (ROOT / folder).rglob("*.py")
                 if "__pycache__" not in p.parts)


def undocumented(path: Path) -> list[str]:
    """Names (with line numbers) of everything in ``path`` lacking a docstring."""
    tree = ast.parse(path.read_text())
    rel = path.relative_to(ROOT)
    missing = [] if ast.get_docstring(tree) else [f"{rel}: module"]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not ast.get_docstring(node):
            missing.append(f"{rel}:{node.lineno} {node.name}")
    return missing


def test_everything_has_a_docstring():
    """No module, class or function in the add-on or its tests lacks a docstring."""
    assert SOURCES, "found no source files"
    missing = [m for path in SOURCES for m in undocumented(path)]
    assert not missing, "missing docstrings:\n" + "\n".join(missing)


def test_summaries_fit_on_one_line():
    """Each docstring starts with a one-line summary (PEP 257)."""
    wrapped = []
    for path in SOURCES:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                doc = ast.get_docstring(node)
                if doc and "\n" in doc.split("\n\n")[0]:
                    wrapped.append(f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', 1)}")
    assert not wrapped, "summary wraps onto a second line:\n" + "\n".join(wrapped)
