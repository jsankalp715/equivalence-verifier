"""Load a function from a `path/to/file.py:function_name` spec."""

from __future__ import annotations

import importlib.util
import inspect
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class LoadedFunction:
    func: Callable
    source_path: Path
    qualified_name: str
    signature: inspect.Signature


def parse_spec(spec: str) -> tuple[Path, str]:
    """Split `path/to/file.py:func_name` into (Path, func_name)."""
    if ":" not in spec:
        raise ValueError(
            f"Expected 'path/to/file.py:function_name', got {spec!r}. "
            "Missing ':function_name' suffix."
        )
    # rsplit so Windows drive letters (D:) don't confuse us
    path_str, func_name = spec.rsplit(":", 1)
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")
    if not func_name.isidentifier():
        raise ValueError(f"Not a valid Python identifier: {func_name!r}")
    return path, func_name


def load_function(spec: str) -> LoadedFunction:
    path, func_name = parse_spec(spec)

    # Unique module name so loading old.py and new.py with the same basename
    # from different directories doesn't collide in sys.modules.
    mod_name = f"_verifier_loaded_{uuid.uuid4().hex}"
    module_spec = importlib.util.spec_from_file_location(mod_name, path)
    if module_spec is None or module_spec.loader is None:
        raise ImportError(f"Could not build import spec for {path}")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[mod_name] = module
    try:
        module_spec.loader.exec_module(module)
    except Exception as e:
        raise ImportError(f"Failed to execute {path}: {e}") from e

    if not hasattr(module, func_name):
        raise AttributeError(
            f"{path} has no attribute {func_name!r}. "
            f"Available: {sorted(n for n in dir(module) if not n.startswith('_'))}"
        )
    func = getattr(module, func_name)
    if not callable(func):
        raise TypeError(f"{func_name} in {path} is not callable")

    return LoadedFunction(
        func=func,
        source_path=path,
        qualified_name=f"{path.name}:{func_name}",
        signature=inspect.signature(func),
    )


def check_signatures_compatible(old: LoadedFunction, new: LoadedFunction) -> None:
    """Warn/raise if the two functions do not have the same parameter names."""
    old_params = list(old.signature.parameters.keys())
    new_params = list(new.signature.parameters.keys())
    if old_params != new_params:
        raise ValueError(
            f"Signature mismatch:\n"
            f"  {old.qualified_name} params: {old_params}\n"
            f"  {new.qualified_name} params: {new_params}\n"
            "Both functions must accept the same parameters by name."
        )
