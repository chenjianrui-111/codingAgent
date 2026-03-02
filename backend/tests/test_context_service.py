from app.services.context_service import ContextIndexer


class DummyRepo:
    pass


def test_extract_python_symbols_and_dependencies():
    indexer = ContextIndexer(repo=DummyRepo())
    content = """
import os
from typing import Any

class UserService:
    \"\"\"service doc\"\"\"
    pass

def run_task(arg1, arg2):
    return arg1 + arg2
"""
    symbols, deps = indexer._extract_python(content, "repo", "main", "a.py")
    names = {s.symbol_name for s in symbols}
    assert "UserService" in names
    assert "run_task" in names

    targets = {d.target_module for d in deps}
    assert "os" in targets
    assert "typing" in targets


def test_extract_ts_symbols_and_dependencies():
    indexer = ContextIndexer(repo=DummyRepo())
    content = """
import { x } from 'lib/core';
const fs = require('fs');
class Demo {}
function build(a, b) { return a + b; }
"""
    symbols, deps = indexer._extract_ts_js(content, "repo", "main", "b.ts")
    names = {s.symbol_name for s in symbols}
    assert "Demo" in names
    assert "build" in names

    targets = {d.target_module for d in deps}
    assert "lib/core" in targets
    assert "fs" in targets
