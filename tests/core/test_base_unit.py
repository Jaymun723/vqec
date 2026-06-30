import numpy as np

from vqec.adapters.circuit_constructors import StimCircuit
from vqec.adapters.noise import DepolarizingNoise
from vqec.adapters.runners import StimRunner
from vqec.core.base import AdapterParams, Decoder, Runner


def test_circuit_build_is_cached():
    circuit = StimCircuit(name="repetition_code:memory", distance=3, rounds=2)
    first = circuit.build()
    second = circuit.build()
    assert first is second


def test_noise_get_is_cached_per_circuit():
    circuit = StimCircuit(name="repetition_code:memory", distance=3, rounds=2)
    noise = DepolarizingNoise(p=0.01)
    first = noise.get(circuit)
    second = noise.get(circuit)
    assert first is second


def test_runner_default_result_metadata():
    class MetaRunner(Runner):
        name = "_meta_runner"

        class Params(AdapterParams):
            pass

        def run(self, circuit_constructor, noise_model):
            return np.zeros(1, dtype=bool)

    assert MetaRunner().result_metadata() == {}


def test_decoder_default_result_metadata():
    class MetaDecoder(Decoder):
        name = "_meta_decoder"

        class Params(AdapterParams):
            pass

        def decode(self, measurements, noise_model, circuit_constructor):
            return np.zeros(1, dtype=bool)

    assert MetaDecoder().result_metadata() == {}


def test_runner_setup_teardown_hooks():
    circuit = StimCircuit(name="repetition_code:memory", distance=3, rounds=2)
    noise = DepolarizingNoise(p=0.01)
    runner = StimRunner(shots=5, seed=0)
    runner.setup(circuit)
    measurements = runner.run(circuit, noise)
    runner.teardown()
    assert measurements["detectors"].shape[0] == 5
