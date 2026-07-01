"""
Central registry for all adapter base classes.

Adapters self-register the moment their module is imported.
Users never call anything here directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from vqec.core.base import (
        CircuitConstructor,
        Decoder,
        NoiseModel,
        Runner,
    )

T = TypeVar("T")


class ComponentRegistry(Generic[T]):
    """Generic registry for library components (for backward compatibility)."""

    def __init__(self) -> None:
        self._items: dict[str, T] = {}

    def register(self, name: str, item: T, overwrite: bool = False) -> None:
        if not overwrite and name in self._items:
            raise ValueError(f"'{name}' already registered.")
        self._items[name] = item

    def get(self, name: str) -> T:
        if name not in self._items:
            raise KeyError(f"Unknown component '{name}'. Available: {list(self._items.keys())}")
        return self._items[name]

    def list_names(self) -> list[str]:
        return sorted(self._items.keys())


class _Registry(Generic[T]):
    """A typed name → class registry for one adapter category."""

    def __init__(self, category: str) -> None:
        self._category = category
        self._store: dict[str, type[T]] = {}

    def register(self, cls: type[T]) -> None:
        # Abstract base classes (no `name` attr or name starts with _) are skipped.
        name = getattr(cls, "name", None)
        if name is None:
            # Fall back to snake_case of class name
            import re

            name = re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()
            cls.name = name  # type: ignore[attr-defined]
        if not name.startswith("_"):
            self._store[name] = cls

    def get(self, name: str) -> type[T]:
        if name not in self._store:
            raise KeyError(
                f"No {self._category} registered under '{name}'. "
                f"Available: {sorted(self._store)}"
            )
        return self._store[name]

    def all(self) -> dict[str, type[T]]:
        return dict(self._store)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Registry[{self._category}] {sorted(self._store)}>"


# One global registry per adapter type
circuit_registry: _Registry[CircuitConstructor] = _Registry("CircuitConstructor")
noise_registry: _Registry[NoiseModel] = _Registry("NoiseModel")
runner_registry: _Registry[Runner] = _Registry("Runner")
decoder_registry: _Registry[Decoder] = _Registry("Decoder")


import vqec.adapters.circuit_constructors
import vqec.adapters.noise
import vqec.adapters.runners
import vqec.adapters.decoders
