"""
Abstract base classes for all four adapter types.

Users subclass these. The metaclass hook (__init_subclass__) handles
registration automatically — no decorators or explicit calls needed.

Pydantic is used for parameter declaration:
  - each adapter defines a nested `Params` model (a pydantic BaseModel)
  - the framework reads Params to validate configs and auto-generate WebUI forms
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import inspect
from typing import Any, ClassVar, TypeAlias, Literal
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict


# ── helpers ───────────────────────────────────────────────────────────────────


class AdapterParams(BaseModel):
    """Base class for all adapter nested Params models, pre-configured with extra='forbid'."""

    model_config = {"extra": "forbid"}


class _NoParams(AdapterParams):
    """Sentinel used when an adapter declares no parameters."""

    pass


# ── CircuitConstructor ────────────────────────────────────────────────────────


class CircuitConstructor(ABC):
    """
    Defines a family of QEC circuits parameterised by e.g. distance, rounds.

    Subclass contract
    -----------------
    - Define a nested ``Params`` pydantic model (subclassing AdapterParams) with all circuit parameters.
    - Optionally implement ``build()`` to cache a concrete circuit object (e.g. stim.Circuit).
    - Optionally set ``name`` (defaults to snake_case of class name).

    Example
    -------
    class SurfaceCode(CircuitConstructor):
        name = "surface_code"

        class Params(AdapterParams):
            distance: int = Field(..., ge=2, description="Code distance")
            rounds:   int = Field(..., ge=1, description="Measurement rounds")
    """

    # Override in subclass if you want an explicit name; otherwise snake_case
    # of the class name is used.
    name: str = "_base_circuit"

    # Each concrete subclass MUST define a nested Params model.
    Params: type[AdapterParams] = _NoParams

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        from vqec.core.registry import circuit_registry

        circuit_registry.register(cls)

    def __init__(self, **params: Any) -> None:
        self.params: AdapterParams = self.__class__.Params(**params)

    def build(self) -> Any:
        """
        Build a concrete circuit object (e.g. stim.Circuit) from the parameters.
        Uses automatic caching so that the underlying _build() method is only called once.
        """
        if not hasattr(self, "_cached_built") or self._cached_built is None:
            self._cached_built = self._build()
        return self._cached_built

    @abstractmethod
    def _build(self) -> Any:
        """
        Subclass hook to build the actual concrete circuit object.
        """

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{self.__class__.__name__} {self.params.model_dump()}>"


# ── NoiseModel ────────────────────────────────────────────────────────────────


class NoiseModel(ABC):
    """
    Parameterises noise applied to a circuit family.

    Subclass contract
    -----------------
    - Declare ``compatible_circuit_constructors`` (set of circuit constructor names) or leave empty for any.
    - Define a nested ``Params`` pydantic model.
    - Implement ``get(circuit_constructor)``.

    The sweep engine will instantiate this class once per sweep point,
    so ``Params`` fields that carry the sweep variable (e.g. ``p``) are
    ordinary scalar fields — the sweep expansion happens at the job level.

    Example
    -------
    class DepolarizingNoise(NoiseModel):
        name = "depolarizing"
        compatible_circuit_constructors: set[str] = set()   # works with any circuit

        class Params(BaseModel):
            p: float = Field(..., ge=0, le=1, description="Depolarizing rate")

        def get(self, circuit_constructor: CircuitConstructor) -> Any:
            ...
    """

    name: str = "_base_noise"
    Params: type[AdapterParams] = _NoParams

    # Empty set means "compatible with every circuit".
    compatible_circuit_constructors: set[str] = set()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        from vqec.core.registry import noise_registry

        noise_registry.register(cls)

    def __init__(self, **params: Any) -> None:
        self.params: AdapterParams = self.__class__.Params(**params)

    def get(self, circuit_constructor: CircuitConstructor) -> Any:
        """
        Return a *noisy* version of the circuit.
        Uses automatic caching so that the underlying _get() method is only called once.
        """
        cc_id = id(circuit_constructor)
        if not hasattr(self, "_cached_noisy") or self._cached_noisy is None:
            self._cached_noisy = {}
        if cc_id not in self._cached_noisy:
            self._cached_noisy[cc_id] = self._get(circuit_constructor)
        return self._cached_noisy[cc_id]

    @abstractmethod
    def _get(self, circuit_constructor: CircuitConstructor) -> Any:
        """
        Subclass hook to apply noise to the circuit constructor.
        """

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{self.__class__.__name__} {self.params.model_dump()}>"


# ── Runner ────────────────────────────────────────────────────────────────────


class Runner(ABC):
    """
    Executes a (circuit, noise_model) pair and returns raw syndrome samples.

    Subclass contract
    -----------------
    - Declare ``compatible_circuit_constructors`` and ``compatible_noise_models`` or leave empty.
    - Define a nested ``Params`` model (e.g. shots).
    - Implement ``run()``.
    - Optionally implement ``setup()`` / ``teardown()`` for expensive one-time work.
    - Optionally implement ``result_metadata()`` to store extra columns.

    Remarks
    -------
    - The Runner is stateless between jobs: it receives a circuit constructor
      instance and a noise model instance for each call to ``run()``. The
      JobBackend may call ``run()`` in parallel across sweep points.
    - The methods ``build()`` of the CircuitConstructor and ``get()`` of the
      NoiseModel are called before this, so you can access the built circuit
      and noise if needed.
    """

    name: str = "_base_runner"
    Params: type[AdapterParams] = _NoParams

    compatible_circuit_constructors: set[str] = set()
    compatible_noise_models: set[str] = set()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        from vqec.core.registry import runner_registry

        runner_registry.register(cls)

    def __init__(self, **params: Any) -> None:
        self.params: AdapterParams = self.__class__.Params(**params)

    # ── optional lifecycle hooks ───────────────────────────────────────────

    def setup(self, circuit_constructor: CircuitConstructor) -> None:
        """
        Called once per job before ``run()``.
        Use for expensive one-time work: histogramming, precomputing, etc.
        """

    def teardown(self) -> None:
        """Called after ``run()`` completes. Release resources."""

    # ── required ──────────────────────────────────────────────────────────

    @abstractmethod
    def run(
        self,
        circuit_constructor: CircuitConstructor,
        noise_model: NoiseModel,
    ) -> Any:
        """
        Execute the circuit under the noise model.

        Returns
        -------
        Anything that can be passed to the compatible Decoder's ``decode()``.
        """

    def result_metadata(self) -> dict[str, Any]:
        """
        Extra key/value pairs stored alongside the results.
        E.g. runner version, timings, etc.
        """
        return {}

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{self.__class__.__name__} {self.params.model_dump()}>"


# ── Decoder ───────────────────────────────────────────────────────────────────


class Decoder(ABC):
    """
    Consumes syndromes and predicts logical error corrections.

    Subclass contract
    -----------------
    - Declare ``compatible_runners``, ``compatible_noise_models``,
      ``compatible_circuit_constructors`` or leave empty for "any".
    - Define a nested ``Params`` model.
    - Implement ``decode()``.
    - Optionally implement ``setup()`` / ``teardown()`` for expensive one-time work.
    - Optionally implement ``result_metadata()`` to store extra columns.
    """

    name: str = "_base_decoder"
    Params: type[AdapterParams] = _NoParams

    compatible_runners: set[str] = set()
    compatible_noise_models: set[str] = set()
    compatible_circuit_constructors: set[str] = set()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        from vqec.core.registry import decoder_registry

        decoder_registry.register(cls)

    def __init__(self, **params: Any) -> None:
        self.params: AdapterParams = self.__class__.Params(**params)

    # ── optional lifecycle hooks ───────────────────────────────────────────

    def setup(self, circuit_constructor: CircuitConstructor, noise_model: NoiseModel) -> None:
        """
        Called once per job before ``decode()``.
        Use for expensive one-time work: build matching graphs, load ML models, etc.
        """

    def teardown(self) -> None:
        """Called after ``decode()`` completes. Release resources."""

    # ── required ──────────────────────────────────────────────────────────

    @abstractmethod
    def decode(
        self,
        measurements: Any,  # (shots, n_observables)
        noise_model: NoiseModel,
        circuit_constructor: CircuitConstructor,
    ) -> np.ndarray:  # (shots,) bool — True = logical error
        """
        Predict whether a logical error occurred for each shot.

        Parameters
        ----------
        measurements : the raw output of the Runner's ``run()`` method for this sweep point
        noise_model : the NoiseModel instance used for this sweep point
        circuit : the CircuitConstructor instance used for this sweep point

        Returns
        -------
        logical_errors : (shots,) bool array
        """

    def result_metadata(self) -> dict[str, Any]:
        """
        Extra key/value pairs stored alongside the logical error rate in results.
        E.g. decoder library version, internal timing, graph statistics.
        """
        return {}

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{self.__class__.__name__} {self.params.model_dump()}>"
