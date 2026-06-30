from __future__ import annotations

import stim
from pydantic import Field
import qec_loss

from vqec.core.base import AdapterParams, CircuitConstructor, NoiseModel


class SpamClifford(NoiseModel):
    """
    Separate error rates for Clifford gates and SPAM (State Prep And Measurement).
    """

    name = "spam_clifford"
    compatible_circuit_constructors = {"stim_circuit_constructor", "physical_circuit_constructor"}

    class Params(AdapterParams):
        after_clifford_depolarization: float = Field(
            ...,
            ge=0.0,
            le=1.0,
            description="Depolarizing error rate applied after Clifford gates",
        )
        spam_flip_probability: float = Field(
            ...,
            ge=0.0,
            le=1.0,
            description="State preparation and measurement flip error rate",
        )

    def _get(self, circuit_constructor: CircuitConstructor) -> stim.Circuit:
        circuit = circuit_constructor.build()
        if not isinstance(circuit, stim.Circuit):
            raise TypeError(f"SpamClifford noise model requires a stim.Circuit, got {type(circuit)}")
        return self._apply(circuit)

    def _apply(self, circuit: stim.Circuit) -> stim.Circuit:
        noisy_circuit = stim.Circuit()
        p_clifford = self.params.after_clifford_depolarization
        p_spam = self.params.spam_flip_probability

        for inst in circuit:
            if isinstance(inst, stim.CircuitRepeatBlock):
                noisy_body = self._apply(inst.body_copy())
                noisy_circuit.append(stim.CircuitRepeatBlock(inst.repeat_count, noisy_body))
                continue

            name = inst.name
            targets = inst.targets_copy()

            if name in ["M", "MR"]:
                noisy_circuit.append("X_ERROR", targets, p_spam)
            elif name == "MX":
                noisy_circuit.append("Z_ERROR", targets, p_spam)

            noisy_circuit.append(inst)

            if name in {
                "H",
                "X",
                "Y",
                "Z",
                "I",
                "SQRT_X",
                "SQRT_X_DAG",
                "SQRT_Y",
                "SQRT_Y_DAG",
                "SQRT_Z",
                "SQRT_Z_DAG",
                "S",
                "S_DAG",
            }:
                noisy_circuit.append("DEPOLARIZE1", targets, p_clifford)
            elif name in {"CX", "CZ", "CY", "CNOT", "CPHASE"}:
                noisy_circuit.append("DEPOLARIZE2", targets, p_clifford)
            elif name in ["R", "MR"]:
                noisy_circuit.append("X_ERROR", targets, p_spam)
            elif name == "RX":
                noisy_circuit.append("Z_ERROR", targets, p_spam)

        return noisy_circuit


class DepolarizingNoise(NoiseModel):
    """
    A simple uniform depolarizing noise model.
    """

    name = "depolarizing_noise"
    compatible_circuit_constructors = {"stim_circuit_constructor", "physical_circuit_constructor"}

    class Params(AdapterParams):
        p: float = Field(..., ge=0.0, le=1.0, description="Uniform depolarization probability")

    def _get(self, circuit_constructor: CircuitConstructor) -> stim.Circuit:
        circuit = circuit_constructor.build()
        if not isinstance(circuit, stim.Circuit):
            raise TypeError(f"DepolarizingNoise requires a stim.Circuit, got {type(circuit)}")
        return self._apply(circuit)

    def _apply(self, circuit: stim.Circuit) -> stim.Circuit:
        p = self.params.p
        if p <= 0:
            return circuit

        noisy_circuit = stim.Circuit()

        for inst in circuit:
            if isinstance(inst, stim.CircuitRepeatBlock):
                noisy_body = self._apply(inst.body_copy())
                noisy_circuit.append(stim.CircuitRepeatBlock(inst.repeat_count, noisy_body))
                continue

            name = inst.name
            targets = inst.targets_copy()

            if name in ["M", "MR"]:
                noisy_circuit.append("X_ERROR", targets, p)

            noisy_circuit.append(inst)

            if name in {
                "H",
                "X",
                "Y",
                "Z",
                "I",
                "SQRT_X",
                "SQRT_X_DAG",
                "SQRT_Y",
                "SQRT_Y_DAG",
                "SQRT_Z",
                "SQRT_Z_DAG",
                "S",
                "S_DAG",
            }:
                noisy_circuit.append("DEPOLARIZE1", targets, p)
            elif name in {"CX", "CZ", "CY", "CNOT", "CPHASE"}:
                noisy_circuit.append("DEPOLARIZE2", targets, p)
            elif name in ["R", "MR"]:
                noisy_circuit.append("X_ERROR", targets, p)

        return noisy_circuit


class LossNoise(DepolarizingNoise):
    """
    Noise model for loss in surface code circuits.
    """

    name = "loss_noise"
    compatible_circuit_constructors = {"stim_circuit_constructor", "physical_circuit_constructor"}

    class Params(AdapterParams):
        loss_2_qubit_gate: float = Field(..., ge=0.0, le=1.0, description="Two-qubit gate loss probability")
        depolarization: float = Field(..., ge=0.0, le=1.0, description="Depolarization probability")

    def _get(self, circuit_constructor: CircuitConstructor) -> stim.Circuit:
        circuit = circuit_constructor.build()
        if not isinstance(circuit, stim.Circuit):
            raise TypeError(f"DepolarizingNoise requires a stim.Circuit, got {type(circuit)}")
        return self._apply(circuit)

    def _apply(self, circuit: stim.Circuit) -> qec_loss.LossyCircuit:
        noisy_circuit = stim.Circuit()

        if self.params.depolarization > 0:
            for inst in circuit.flattened():
                name = inst.name
                targets = inst.targets_copy()

                noisy_circuit.append(inst)

                if name in {
                    "H",
                    "X",
                    "Y",
                    "Z",
                    "I",
                    "SQRT_X",
                    "SQRT_X_DAG",
                    "SQRT_Y",
                    "SQRT_Y_DAG",
                    "SQRT_Z",
                    "SQRT_Z_DAG",
                    "S",
                    "S_DAG",
                }:
                    noisy_circuit.append("DEPOLARIZE1", targets, self.params.depolarization)
                elif name in {"CX", "CZ", "CY", "CNOT", "CPHASE"}:
                    noisy_circuit.append("DEPOLARIZE2", targets, self.params.depolarization)
                elif name in ["R", "MR"]:
                    noisy_circuit.append("X_ERROR", targets, self.params.depolarization)
        else:
            noisy_circuit = circuit.flattened()

        return qec_loss.add_loss_noise(noisy_circuit, loss_before_2_qubit_gate=self.params.loss_2_qubit_gate)
