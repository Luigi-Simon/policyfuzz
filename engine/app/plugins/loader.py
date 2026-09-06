"""Load optional person-3 / person-4 plugins from dotted paths."""

from __future__ import annotations

import importlib
from typing import Any


class PluginError(RuntimeError):
    pass


def load_plugin(spec: str) -> Any:
    """Load `package.module:ClassName`."""
    if not spec or ":" not in spec:
        raise PluginError(f"Invalid plugin spec: {spec!r}")
    module_name, _, class_name = spec.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as error:
        raise PluginError(f"Cannot import plugin module {module_name}: {error}") from error
    try:
        cls = getattr(module, class_name)
    except AttributeError as error:
        raise PluginError(f"{module_name} has no {class_name}") from error
    return cls()
