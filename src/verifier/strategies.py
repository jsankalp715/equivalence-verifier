"""Infer Hypothesis strategies from a function's type hints, or load them from a spec file."""

from __future__ import annotations

import importlib.util
import inspect
import sys
import typing
import uuid
from pathlib import Path
from typing import Any, get_args, get_origin

from hypothesis import strategies as st


class StrategyInferenceError(Exception):
    """Raised when we can't infer a Hypothesis strategy for a parameter."""


def _strategy_for_annotation(ann: Any) -> st.SearchStrategy:
    """Map a type annotation to a default Hypothesis strategy.

    Conservative defaults: floats/ints are bounded to values that produce
    intelligible counterexamples (no NaN, no infinity, no runaway magnitudes).
    Users who want wider domains should provide a strategies spec file.
    """
    if ann is inspect.Parameter.empty:
        raise StrategyInferenceError(
            "No type hint provided. Add a type annotation or supply a strategies spec file."
        )

    origin = get_origin(ann)
    args = get_args(ann)

    if ann is int:
        return st.integers(min_value=-10_000, max_value=10_000)
    if ann is float:
        return st.floats(
            min_value=-1e6, max_value=1e6,
            allow_nan=False, allow_infinity=False,
        )
    if ann is bool:
        return st.booleans()
    if ann is str:
        return st.text(max_size=50)
    if ann is bytes:
        return st.binary(max_size=50)
    if ann is type(None):
        return st.none()

    if origin is list:
        (elem_t,) = args or (int,)
        return st.lists(_strategy_for_annotation(elem_t), max_size=20)
    if origin is tuple:
        if not args:
            return st.tuples()
        # tuple[X, ...] = homogeneous variable-length
        if len(args) == 2 and args[1] is Ellipsis:
            return st.lists(_strategy_for_annotation(args[0]), max_size=10).map(tuple)
        return st.tuples(*(_strategy_for_annotation(a) for a in args))
    if origin is dict:
        key_t, val_t = args or (str, int)
        return st.dictionaries(
            _strategy_for_annotation(key_t),
            _strategy_for_annotation(val_t),
            max_size=10,
        )
    if origin is set:
        (elem_t,) = args or (int,)
        return st.sets(_strategy_for_annotation(elem_t), max_size=10)

    # Optional[X] / Union[X, None]
    if origin is typing.Union:
        substrats = [_strategy_for_annotation(a) for a in args]
        return st.one_of(*substrats)

    raise StrategyInferenceError(
        f"No default strategy for annotation {ann!r}. "
        "Provide one via a strategies spec file."
    )


def infer_strategies(signature: inspect.Signature) -> dict[str, st.SearchStrategy]:
    """Return {param_name: strategy} for every parameter in `signature`."""
    strategies: dict[str, st.SearchStrategy] = {}
    for name, param in signature.parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            raise StrategyInferenceError(
                f"Parameter {name!r} is *args/**kwargs; not supported in v1. "
                "Wrap the function or supply a strategies spec file."
            )
        try:
            strategies[name] = _strategy_for_annotation(param.annotation)
        except StrategyInferenceError as e:
            raise StrategyInferenceError(f"Parameter {name!r}: {e}") from e
    return strategies


def load_spec_file(path: Path) -> dict[str, st.SearchStrategy]:
    """Import a Python file and return its `strategies` dict.

    The file must define a module-level `strategies: dict[str, SearchStrategy]`.
    """
    if not path.exists():
        raise FileNotFoundError(f"Strategy spec file not found: {path}")

    mod_name = f"_verifier_strategy_spec_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not import strategy spec {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)

    if not hasattr(module, "strategies"):
        raise AttributeError(
            f"{path} does not define a top-level `strategies` dict."
        )
    strategies = module.strategies
    if not isinstance(strategies, dict):
        raise TypeError(f"`strategies` in {path} must be a dict, got {type(strategies).__name__}")
    for name, strat in strategies.items():
        if not isinstance(strat, st.SearchStrategy):
            raise TypeError(
                f"strategies[{name!r}] must be a Hypothesis SearchStrategy, "
                f"got {type(strat).__name__}"
            )
    return strategies


def resolve_strategies(
    signature: inspect.Signature,
    spec_file: Path | None,
) -> dict[str, st.SearchStrategy]:
    """Load strategies from a spec file if given, otherwise infer from type hints.

    A spec file must cover every parameter in the signature. Extra keys in the
    spec are an error (probably a typo).
    """
    param_names = [
        n for n, p in signature.parameters.items()
        if p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    ]

    if spec_file is None:
        return infer_strategies(signature)

    loaded = load_spec_file(spec_file)
    missing = set(param_names) - set(loaded.keys())
    extra = set(loaded.keys()) - set(param_names)
    if missing:
        raise ValueError(f"Strategy spec missing keys: {sorted(missing)}")
    if extra:
        raise ValueError(f"Strategy spec has unknown keys: {sorted(extra)}")
    return {n: loaded[n] for n in param_names}
