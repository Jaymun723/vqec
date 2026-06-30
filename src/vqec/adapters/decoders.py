from pathlib import Path
from typing import Any, Literal

import numpy as np
import pymatching
import qec_loss
from pydantic import Field

from vqec.core.base import AdapterParams, CircuitConstructor, Decoder, NoiseModel

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBClassifier


class PyMatching(Decoder):
    """
    Minimum-weight perfect matching (MWPM) decoder using PyMatching.
    """

    name = "pymatching"
    compatible_runners: set[str] = {"stim_runner"}

    class Params(AdapterParams):
        num_neighbours: int = Field(
            30,
            ge=1,
            description="Number of neighbours used when building the matching graph.",
        )
        max_edge_weight: float = Field(
            1e6,
            gt=0.0,
            description="Cap on matching graph edge weights.",
        )

    def __init__(self, **params: Any) -> None:
        super().__init__(**params)
        self._matcher = None

    def teardown(self) -> None:
        self._matcher = None

    def decode(
        self,
        measurements: Any,
        noise_model: NoiseModel,
        circuit_constructor: CircuitConstructor,
    ) -> np.ndarray:
        syndromes = measurements["detectors"]
        observables = measurements["observables"]

        if self._matcher is None:
            noisy_circuit = noise_model.get(circuit_constructor)
            dem = noisy_circuit.detector_error_model(decompose_errors=True)
            self._matcher = pymatching.Matching.from_detector_error_model(dem)

        syndromes_uint8 = syndromes.astype(np.uint8)
        syndromes_packed = np.packbits(syndromes_uint8, axis=1, bitorder="little")
        predictions = self._matcher.decode_batch(syndromes_packed, bit_packed_shots=True, bit_packed_predictions=True)
        predictions_unpack = np.unpackbits(predictions, axis=1, bitorder="little")[:, : observables.shape[1]]
        return (predictions_unpack != observables).any(axis=1)

    def result_metadata(self) -> dict[str, Any]:
        return {"pymatching_version": pymatching.__version__}


class MonakaDecoder(Decoder):
    """
    Monaka decoding for qec-loss.
    """

    name = "monaka_decoder"
    compatible_runners: set[str] = {"qec_loss_runner"}
    compatible_noise_models: set[str] = {"loss_noise"}
    compatible_circuit_constructors: set[str] = {"stim_circuit_constructor", "physical_circuit_constructor"}

    class Params(AdapterParams):
        include_loss_dem: bool = Field(
            True,
            description="Whether to include loss events in the DEM for decoding.",
        )
        post_select_usable_events: bool = Field(
            False,
            description="Whether to post-select on usable events. If False, unusable events count as logical errors.",
        )

    def setup(self, circuit_constructor: CircuitConstructor, noise_model: NoiseModel) -> None:
        circuit = noise_model.get(circuit_constructor)
        self.monaka = qec_loss.MonakaBuilder(circuit)

    def decode(
        self,
        measurements: Any,
        noise_model: NoiseModel,
        circuit_constructor: CircuitConstructor,
    ) -> np.ndarray:

        preds = self.monaka.decode_batch(measurements, include_loss_dem=self.params.include_loss_dem)

        mask = measurements.observables != 2

        if not self.params.post_select_usable_events:
            return preds[mask] != measurements.observables[mask]
        else:
            return preds != measurements.observables


class XGBDecoder(Decoder):
    """
    XGBoost decoder.
    """

    name = "xgb_decoder"
    compatible_runners: set[str] = {"qec_loss_runner"}
    compatible_noise_models: set[str] = {"loss_noise"}
    compatible_circuit_constructors: set[str] = {"stim_circuit_constructor", "physical_circuit_constructor"}

    class Params(AdapterParams):
        test_size: float = Field(
            0.2,
            ge=0.0,
            le=1.0,
            description="Fraction of data to use for testing.",
        )
        one_hot_encode: bool = Field(
            True,
            description="Whether to one-hot encode the input features.",
        )
        post_select_usable_events: bool = Field(
            False,
            description="Whether to post-select on usable events. If False, unusable events count as logical errors.",
        )
        max_depth: int = Field(
            6,
            ge=1,
            description="Maximum depth of the trees.",
        )
        min_child_weight: float = Field(
            1.0,
            ge=0.0,
            description="Minimum sum of instance weight (hessian) needed in a child.",
        )
        gamma: float = Field(
            0.2,
            ge=0.0,
            description="Minimum loss reduction required to make a further partition on a leaf node of the tree.",
        )
        colsample_bytree: float = Field(
            1.0,
            ge=0.0,
            le=1.0,
            description="Subsample ratio of columns when constructing each tree.",
        )
        n_estimators: int = Field(
            300,
            ge=1,
            description="Number of trees in the ensemble.",
        )
        learning_rate: float = Field(
            0.07,
            ge=0.0,
            description="Boosting learning rate.",
        )

    def setup(self, circuit_constructor: CircuitConstructor, noise_model: NoiseModel) -> None:
        self.model = XGBClassifier(
            max_depth=self.params.max_depth,
            min_child_weight=self.params.min_child_weight,
            gamma=self.params.gamma,
            colsample_bytree=self.params.colsample_bytree,
            objective="binary:logistic",
            early_stopping_rounds=10,
            n_estimators=self.params.n_estimators,
            learning_rate=self.params.learning_rate,
        )

    def decode(
        self,
        measurements: Any,
        noise_model: NoiseModel,
        circuit_constructor: CircuitConstructor,
    ) -> np.ndarray:
        X = np.hstack([measurements.measurements, measurements.detectors])
        y = measurements.observables

        if self.params.one_hot_encode:
            encoder = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
            X = encoder.fit_transform(X)

        if self.params.post_select_usable_events:
            mask = measurements.observables != 2
            X = X[mask]
            y = y[mask]

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=self.params.test_size, random_state=42)

        self.model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

        preds = self.model.predict(X)

        return preds != y
