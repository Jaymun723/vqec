from __future__ import annotations

from typing import Any

import numpy as np
import stim
import qec_loss
from pydantic import Field

from vqec.core.base import AdapterParams, CircuitConstructor, NoiseModel, Runner


class StimRunner(Runner):
    """
    Runs stim circuits and collects detector syndrome and observable samples.
    """

    name = "stim_runner"

    compatible_circuit_constructors = {"stim_circuit_constructor", "physical_circuit_constructor"}
    compatible_noise_models = {"depolarizing_noise", "spam_clifford"}

    class Params(AdapterParams):
        shots: int = Field(100_000, ge=1, description="Number of shots (samples)")
        seed: int | None = Field(None, description="RNG seed for reproducibility. None = random.")

    def run(
        self,
        circuit_constructor: CircuitConstructor,
        noise_model: NoiseModel,
    ) -> Any:
        noisy_circuit = noise_model.get(circuit_constructor)
        if not isinstance(noisy_circuit, stim.Circuit):
            raise TypeError(f"StimRunner requires a stim.Circuit, got {type(noisy_circuit)}")

        sampler = noisy_circuit.compile_detector_sampler(seed=self.params.seed)
        raw_syndromes, raw_observables = sampler.sample(
            self.params.shots,
            separate_observables=True,
        )
        return {
            "detectors": np.array(raw_syndromes, dtype=bool),
            "observables": np.array(raw_observables, dtype=bool),
        }


class QecLossRunner(Runner):
    """
    Runs qec_loss circuits and collects detector syndrome and observable samples.
    """

    name = "qec_loss_runner"

    compatible_circuit_constructors = {"stim_circuit_constructor", "physical_circuit_constructor"}
    compatible_noise_models = {"loss_noise"}

    class Params(AdapterParams):
        shots: int = Field(10_000, ge=1, description="Number of shots (samples)")
        reroute_observables: bool = Field(True, description="Whether to reroute observables around losses.")
        seed: int | None = Field(None, description="RNG seed for reproducibility. None = random.")

    def run(
        self,
        circuit_constructor: CircuitConstructor,
        noise_model: NoiseModel,
    ) -> Any:
        lossy_circuit = noise_model.get(circuit_constructor)
        if not isinstance(lossy_circuit, qec_loss.LossyCircuit):
            raise TypeError(f"QecLossRunner requires a qec_loss.LossyCircuit, got {type(lossy_circuit)}")

        sampler = qec_loss.ForwardSampler(lossy_circuit, seed=self.params.seed)

        batch = sampler.sample(self.params.shots, reroute_observables=self.params.reroute_observables)

        return batch

        # return {
        #     "measurements": np.array(batch.measurements, dtype=np.uint8),
        #     "detectors": np.array(batch.detectors, dtype=np.uint8),
        #     "observables": np.array(batch.observables, dtype=np.uint8),
        #     "loss_patterns": lossy_circuit.loss_patterns,
        # }
