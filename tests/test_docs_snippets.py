"""Keyword arguments in the docs' Python examples must exist on the SDK methods they call."""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

from astro_mmdc import MMDC

DOCS = Path(__file__).resolve().parent.parent / "docs"
PAGES = ["agents.md", "index.md", "getting-started.md"]
_BLOCK_RE = re.compile(r"^```python\n(.*?)^```", re.M | re.S)


def _blocks(page: str) -> list[str]:
    return _BLOCK_RE.findall((DOCS / page).read_text(encoding="utf-8"))


def _client_calls(tree: ast.AST):
    """Yield (namespace, method, keyword names, node) for every client.<ns>.<method>(...)."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        owner = node.func.value
        if (
            isinstance(owner, ast.Attribute)
            and isinstance(owner.value, ast.Name)
            and owner.value.id == "client"
        ):
            names = [kw.arg for kw in node.keywords if kw.arg is not None]
            yield owner.attr, node.func.attr, names, node


def _cases():
    for page in PAGES:
        for i, block in enumerate(_blocks(page)):
            yield pytest.param(page, block, id=f"{page}#{i}")


@pytest.mark.parametrize(("page", "block"), list(_cases()))
def test_snippet_calls_match_signatures(page: str, block: str) -> None:
    tree = ast.parse(block)  # also catches a snippet that is not valid Python
    client = MMDC()
    try:
        for ns, method, keywords, node in _client_calls(tree):
            resource = getattr(client, ns, None)
            assert resource is not None, f"{page}: client.{ns} does not exist"
            func = getattr(resource, method, None)
            assert callable(func), f"{page}: client.{ns}.{method} does not exist"
            params = inspect.signature(func).parameters
            if any(p.kind is p.VAR_KEYWORD for p in params.values()):
                continue
            unknown = [k for k in keywords if k not in params]
            assert not unknown, (
                f"{page} line {node.lineno}: client.{ns}.{method}() has no "
                f"keyword {', '.join(unknown)}"
            )
    finally:
        client.close()


def test_pages_have_client_calls() -> None:
    # Guards the parser: if the fence format changes, the test above would pass vacuously.
    calls = [c for block in _blocks("agents.md") for c in _client_calls(ast.parse(block))]
    assert len(calls) >= 10
