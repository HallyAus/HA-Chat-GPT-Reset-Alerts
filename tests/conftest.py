"""Load pure integration modules without requiring Home Assistant locally."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "custom_components" / "claude_usage"


def load_module(name: str):
    if "claude_usage" not in sys.modules:
        package = types.ModuleType("claude_usage")
        package.__path__ = [str(PACKAGE)]
        sys.modules["claude_usage"] = package
    full_name = f"claude_usage.{name}"
    if full_name in sys.modules:
        return sys.modules[full_name]
    path = PACKAGE / f"{name}.py"
    spec = importlib.util.spec_from_file_location(full_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module
