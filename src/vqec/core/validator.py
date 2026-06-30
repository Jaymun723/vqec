"""
Compatibility validator.

Checks that the chosen (circuit, noise, runner, decoder) combination
satisfies all declared constraints before any jobs are submitted or
any circuits are built.

All errors are collected and raised together so users see the full
picture in one shot rather than fixing one problem at a time.
"""

from __future__ import annotations

from dataclasses import dataclass

from vqec.core.base import (
    CircuitConstructor,
    Decoder,
    NoiseModel,
    Runner,
)


@dataclass
class ValidationError:
    field: str
    message: str

    def __str__(self) -> str:
        return f"  [{self.field}] {self.message}"


class CompatibilityError(Exception):
    """Raised when the adapter combination violates compatibility constraints."""

    def __init__(self, errors: list[ValidationError]) -> None:
        self.errors = errors
        lines = "\n".join(str(e) for e in errors)
        super().__init__(f"Incompatible adapter combination:\n{lines}")


def validate(
    circuit_constructor: CircuitConstructor,
    noise: NoiseModel,
    runner: Runner,
    decoder: Decoder,
) -> None:
    """
    Raise ``CompatibilityError`` if any constraint is violated.

    Called by the framework before sweep expansion so that config
    mistakes are caught immediately, not mid-run.

    Constraints checked (empty set = "accept anything"):
    - noise.compatible_circuit_constructors ∋ circuit_constructor.name
    - runner.compatible_circuit_constructors ∋ circuit_constructor.name
    - runner.compatible_noise_models   ∋ noise.name
    - decoder.compatible_circuit_constructors ∋ circuit_constructor.name
    - decoder.compatible_noise_models   ∋ noise.name
    - decoder.compatible_runners  ∋ runner.name
    """
    errors: list[ValidationError] = []

    def _check(
        constraint_set: set[str],
        candidate: str,
        owner: str,
        field: str,
    ) -> None:
        if constraint_set and candidate not in constraint_set:
            errors.append(
                ValidationError(
                    field=field,
                    message=(
                        f"{owner} requires one of {sorted(constraint_set)}, got '{candidate}'"
                    ),
                )
            )

    circuit_name = circuit_constructor.__class__.name
    noise_name = noise.__class__.name
    runner_name = runner.__class__.name

    _check(
        noise.__class__.compatible_circuit_constructors,
        circuit_name,
        noise.__class__.__name__,
        "noise → circuit",
    )
    _check(
        runner.__class__.compatible_circuit_constructors,
        circuit_name,
        runner.__class__.__name__,
        "runner → circuit",
    )
    _check(
        runner.__class__.compatible_noise_models,
        noise_name,
        runner.__class__.__name__,
        "runner → noise",
    )
    _check(
        decoder.__class__.compatible_circuit_constructors,
        circuit_name,
        decoder.__class__.__name__,
        "decoder → circuit",
    )
    _check(
        decoder.__class__.compatible_noise_models,
        noise_name,
        decoder.__class__.__name__,
        "decoder → noise",
    )
    _check(
        decoder.__class__.compatible_runners,
        runner_name,
        decoder.__class__.__name__,
        "decoder → runner",
    )

    if errors:
        raise CompatibilityError(errors)
