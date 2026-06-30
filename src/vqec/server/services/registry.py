from typing import Any, Dict, List

from vqec.core.registry import circuit_registry, decoder_registry, noise_registry, runner_registry
from vqec.server.models.schemas import RegistryComponent


def get_all_components() -> Dict[str, List[str]]:
    return {
        "circuit_constructors": sorted(circuit_registry.all().keys()),
        "noise_models": sorted(noise_registry.all().keys()),
        "runners": sorted(runner_registry.all().keys()),
        "decoders": sorted(decoder_registry.all().keys()),
    }


def get_registry_for_category(category: str):
    mapping = {
        "circuit-constructors": circuit_registry,
        "noise-models": noise_registry,
        "runners": runner_registry,
        "decoders": decoder_registry,
    }
    return mapping.get(category)


def _format_compatibility(cls: type) -> Dict[str, List[str]]:
    compatibility: Dict[str, List[str]] = {}
    if hasattr(cls, "compatible_circuit_constructors"):
        compatibility["circuit_constructors"] = sorted(cls.compatible_circuit_constructors)
    if hasattr(cls, "compatible_noise_models"):
        compatibility["noise_models"] = sorted(cls.compatible_noise_models)
    if hasattr(cls, "compatible_runners"):
        compatibility["runners"] = sorted(cls.compatible_runners)
    return compatibility


def _format_component(cls: type, component_name: str) -> RegistryComponent:
    description = ""
    if cls.__doc__:
        description = "\n".join(line.strip() for line in cls.__doc__.strip().splitlines())

    schema: Dict[str, Any] = {}
    if hasattr(cls, "Params") and hasattr(cls.Params, "model_json_schema"):
        schema = cls.Params.model_json_schema()

    return RegistryComponent(
        name=getattr(cls, "name", component_name),
        description=description,
        schema=schema,
        compatibility=_format_compatibility(cls),
    )


def get_category_components(
    category: str,
    circuit_constructor: str | None = None,
    noise_model: str | None = None,
    runner: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> List[RegistryComponent] | None:
    registry = get_registry_for_category(category)
    if not registry:
        return None

    results: List[RegistryComponent] = []
    for name, cls in registry.all().items():
        comp = _format_component(cls, name)
        if circuit_constructor and "circuit_constructors" in comp.compatibility:
            if circuit_constructor not in comp.compatibility["circuit_constructors"]:
                continue
        if noise_model and "noise_models" in comp.compatibility:
            if noise_model not in comp.compatibility["noise_models"]:
                continue
        if runner and "runners" in comp.compatibility:
            if runner not in comp.compatibility["runners"]:
                continue
        results.append(comp)

    return results[offset : offset + limit]


def get_component_detail(category: str, component_name: str) -> RegistryComponent | None:
    registry = get_registry_for_category(category)
    if not registry:
        return None
    try:
        cls = registry.get(component_name)
    except KeyError:
        return None
    return _format_component(cls, component_name)
