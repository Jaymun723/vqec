from __future__ import annotations

import stim
from pydantic import Field

from vqec.core.base import AdapterParams, CircuitConstructor


class StimCircuit(CircuitConstructor):
    """
    Standard stim generator circuits (e.g. repetition_code, surface_code).
    """

    name = "stim_circuit_constructor"

    class Params(AdapterParams):
        name: str = Field(
            ...,
            description="Name of the circuit generator (e.g. 'surface_code:rotated_memory_z')",
        )
        distance: int = Field(..., ge=1, description="Code distance")
        rounds: int = Field(..., ge=0, description="Measurement rounds")

    def _build(self) -> stim.Circuit:
        return stim.Circuit.generated(
            self.params.name,
            distance=self.params.distance,
            rounds=self.params.rounds,
        )


class PhysicalCircuit(CircuitConstructor):
    """
    Unencoded physical memory on `distance` parallel qubits idling for `rounds` rounds.
    """

    name = "physical_circuit_constructor"

    class Params(AdapterParams):
        distance: int = Field(..., ge=1, description="Number of parallel physical qubits")
        rounds: int = Field(..., ge=0, description="Idle rounds")

    def _build(self) -> stim.Circuit:
        if self.params.distance < 1:
            raise ValueError("distance must be at least 1")

        qs = list(range(self.params.distance))
        c = stim.Circuit()
        c.append("R", qs)

        round_body = stim.Circuit()
        round_body.append("TICK")
        round_body.append("I", qs)
        if self.params.rounds > 0:
            c.append(stim.CircuitRepeatBlock(self.params.rounds, round_body))

        c.append("M", qs)

        d = self.params.distance
        c.append(
            "OBSERVABLE_INCLUDE",
            [stim.target_rec(-d + k) for k in range(d)],
            0,
        )
        return c
